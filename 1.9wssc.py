import traceback
import sys
try:
    import cPickle as pickle
except ImportError:
    import _pickle as pickle
import datetime
import unicodedata
import base64
import re

app_name = "Microsoft: Windows Server Service Configuration"
DO_REGEX = True

## Developer customization: Hardcoded exclusion list
exclude_services_list = ['GISvc', 'IaasVmProvider','Windows Service Pack Installer update service','BMR Boot Service','Microsoft .NET Framework NGEN v4.0.30319_X86','Microsoft .NET Framework NGEN v4.0.30319_X64','NetBackup SAN Client Fibre Transport Service','ccmsetup','SeOS Agent','CA Access Control Agent Manager','SeOS Engine','CA Access Control Report Agent','SeOS TD','SeOS Watchdog','EsaEvCrawlerService','EsaEvRetrieverService','EsaExchangeCrawlerService','EsaEvRetrieverService','IGCBravaLicenseService','IGCJobProcessorService','EsaNsfCrawlerService','EsaNsfRetrieverService','EsaPstCrawlerService','EsaPstRetrieverService','AmazonSSMAgent','stisvc']

def get_last_cached_request_result(self, key, is_concurrent, pickling=True):
    try:
        print("[STEP: Cache Query] Key: {}, Concurrent: {}".format(key, is_concurrent))
        collection_time = datetime.datetime.fromtimestamp(self.gmtime)
        expiration_buffer = datetime.timedelta(minutes=11)
        minimum_expire_time = collection_time - expiration_buffer
        
        if is_concurrent:
            query = """SELECT `key`, `value`, `date_updated`, `expires` FROM `cache`.`dynamic_app`
                       WHERE `key` LIKE %s AND `date_updated` <= %s AND %s < `expires`
                       ORDER BY `date_updated` DESC LIMIT 1"""
        else:
            updated_buffer = datetime.timedelta(minutes=3)
            minimum_expire_time = collection_time - updated_buffer
            query = """SELECT `key`, `value`, `date_updated`, `expires` FROM `cache`.`dynamic_app`
                       WHERE `key` LIKE %s AND `date_updated` <= %s AND %s < `date_updated`
                       ORDER BY `date_updated` DESC LIMIT 1"""

        arg = ("%" + key, collection_time, minimum_expire_time)
        self.dbc.execute(query, arg)
        result = self.dbc.fetchall()
      
        if len(result):
            key, result, cache_date_updated, cache_expires = result[0]
            print("[SUCCESS: Cache Hit] Updated: {}, Expires: {}".format(cache_date_updated, cache_expires))
            if pickling:
                try:
                    result = pickle.loads(result)
                except Exception as e:
                    print("[FAILURE: Unpickle] Failed to unpickle result: {}".format(e))
                    return None
            return result
        else:
            print("[INFO: Cache Miss] No valid entry found. Running diagnostic...")
            diag_query = "SELECT `key`, `date_updated`, `expires` FROM `cache`.`dynamic_app` WHERE `key` LIKE %s ORDER BY `date_updated` DESC LIMIT 3"
            self.dbc.execute(diag_query, ("%" + key,))
            diag_results = self.dbc.fetchall()
            if diag_results:
                for d_key, d_updated, d_expires in diag_results:
                    print("[DIAGNOSTIC] Found entry: Key: {}, Updated: {}, Expires: {}".format(d_key, d_updated, d_expires))
            return None
    except Exception:
        print("[CRITICAL: get_last_cached_request_result] Error occurred:\n{}".format(traceback.format_exc()))
        raise

def concurrentps_enabled(self):
    try:
        powershell_service_flag = self.dbc.autofetch_value("""SELECT MAX(field_value+0) FROM master.system_custom_config 
                                            WHERE field LIKE 'enable_powershell_service%'
                                            GROUP BY cug_filter ORDER BY cug_filter DESC LIMIT 1""")
        flag = int(powershell_service_flag) if powershell_service_flag is not None else 0
        print("[INFO: Concurrent PS] Flag Value: {}".format(flag))
        return flag
    except Exception:
        print("[CRITICAL: concurrentps_enabled] Error occurred:\n{}".format(traceback.format_exc()))
        raise

def get_current_cached_request_result(self, req_guid, index_item=None):
    try:
        print("[STEP: Request Lookup] GUID: {}".format(req_guid))
        req = self.dbc.autofetchrow_dict("select app_id, req_id from master.dynamic_app_requests where req_guid='%s'" % req_guid)
        
        if not req:
            print("[ERROR: Request Lookup] No record found for GUID: {}".format(req_guid))
            return None
            
        cache_key = self.cache.generate_key(app_id=req['app_id'], did=self.did, use_timestamp=False, req_id=req['req_id'])
        is_concurrent = concurrentps_enabled(self)
        result = get_last_cached_request_result(self, cache_key, is_concurrent)

        if result is None and not is_concurrent:
            print("[STEP: Parent Collection] Cache miss, initiating collect_parent...")
            parent_sync_key = self.cache.generate_key(app_id=req['app_id'], did=self.did)
            cache_key = self.cache.generate_key(app_id=req['app_id'], req_id=req['req_id'], did=self.did)
            did = self.did if self.did != self.root_did else None
            self.collect_parent(cache_key, req['app_id'], parent_sync_key, did)
            result = self.cache.get(cache_key)
        
        if (result is not None) and (index_item is not None):
            index_mapping = result.get(index_item, {})
            for item in result:
                result[item] = {index_mapping.get(index, index): data for index, data in list(result[item].items())}
        return result
    except Exception:
        print("[CRITICAL: get_current_cached_request_result] Error occurred:\n{}".format(traceback.format_exc()))
        raise

def get_block_list_services(self):
    try:
        sql = "SELECT service_name, did FROM master.definitions_service_autostart_exclude WHERE did in (0,{})".format(self.did)
        blocklist = self.dbc.autofetchall_dict(sql)  
        print("[INFO: Blocklist] Count: {}".format(len(blocklist)))
        return blocklist
    except Exception:
        print("[CRITICAL: get_block_list_services] Error occurred:\n{}".format(traceback.format_exc()))
        raise
    
def is_service_on_blocklist(self, blocklist, serviceName, displayName):
    try:
        for service in blocklist:
            match_pattern = service['service_name']
            try:
                if (match_pattern == serviceName or match_pattern == displayName or
                   (DO_REGEX and (re.search(match_pattern, serviceName) or re.search(match_pattern, displayName)))):
                    print("[INFO: Blocklist Match] Service: {} Pattern: {}".format(serviceName, match_pattern))
                    return 1
            except Exception as e:
                print("[WARN: Blocklist Regex] Format not supported \"{}\", error: {}".format(match_pattern, e))
        return 0
    except Exception:
        print("[CRITICAL: is_service_on_blocklist] Error occurred:\n{}".format(traceback.format_exc()))
        raise

def service_encoding(text):
    if isinstance(text, str): return normalize_unicode(text)
    if isinstance(text, bytes): return normalize_unicode(text.decode("utf-8") if sys.version_info < (3, 0) else text.decode())
    return text

def normalize_unicode(st):
    ascii_str = ""
    for ch in st:
        ascii_ch = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore")
        if sys.version_info >= (3, 0): ascii_ch = ascii_ch.decode()
        if ascii_ch == "":
            c = ch.encode("ascii", "backslashreplace")
            ascii_ch = "[" + (c.decode() if sys.version_info >= (3, 0) else c) + "]"
        ascii_str += ascii_ch
    return ascii_str

def is_ascii(value): return all(ord(c) < 128 for c in value)

def replace_char(service):
    result = service
    for char in service:
        if not is_ascii(char): result = result.replace(char, '')
    return result

########################################
# MAIN EXECUTION BLOCK
########################################

WINDOWS_SERVER_SERVICES_REQ_GUID = '828EFE6D4485860679972EACD7097ED1'
COLLECT_ERROR = 257

try:
    print("[START] Beginning Snippet Execution")
    result = get_current_cached_request_result(self, WINDOWS_SERVER_SERVICES_REQ_GUID, "DisplayName")

    if not result:
        print("[STOP] No data retrieved from cache. Exiting.")
    else:
        print("[STEP: Data Processing] Processing cache results...")
        blocklist = get_block_list_services(self)    
        
        dn = result.get('DisplayName', {})
        n = result.get('Name', {})
        s = result.get('State', {})
        sn = result.get('StartName', {})
        sm = result.get('StartMode', {})
        trigger_val = result.get('Trigger', {})
        delayedautostart = result.get('DelayedAutostart', {})
    
        displayname, name, state, startname, startmode, bl_status, trigger, monitored = [], [], [], [], [], [], [], []

        for key in list(dn.keys()):
            raw_name = n.get(key, "")
            serviceName = raw_name
            try:
                # Robust Base64/Plain-text detection
                if raw_name and not is_ascii(raw_name): serviceName = base64.b64decode(raw_name).decode("utf-8")
                else:
                    try: 
                        decoded = base64.b64decode(raw_name).decode("utf-8")
                        if any(c.isalnum() for c in decoded): serviceName = decoded
                    except: pass
            except: pass

            bl_status_val = is_service_on_blocklist(self, blocklist, serviceName, key)
            is_excluded = any(re.match(pattern, serviceName) for pattern in exclude_services_list)

            if all(key in d for d in [s, n, sn, sm, trigger_val]):
                eIndex = service_encoding(key)
                name_parsed = service_encoding(n[key])
                displayname_parsed = service_encoding(dn[key]) if is_ascii(dn[key]) else service_encoding(replace_char(dn[key]))
                startname_parsed = sn[key] if is_ascii(sn[key]) else replace_char(sn[key])

                displayname.append((eIndex, displayname_parsed))
                name.append((eIndex, name_parsed))
                state.append((eIndex, s[key]))
                startname.append((eIndex, startname_parsed))
                
                # Enhanced StartMode and Monitored detection
                start_mode_str = sm[key]
                is_trig = trigger_val[key] == 'True'
                is_del = delayedautostart.get(key, 'False') == 'True'
                mon_val = 'Yes'

                if is_trig and not is_del:
                    start_mode_str += " (Trigger Start)"
                    mon_val = 'No'
                elif is_trig and is_del:
                    start_mode_str += " (Delayed Start, Trigger Start)"
                    mon_val = 'No'
                elif not is_trig and is_del:
                    start_mode_str += " (Delayed Start)"
                    mon_val = 'No'
                
                if mon_val == 'Yes' and is_excluded:
                    mon_val = 'No'

                trigger.append((eIndex, 'True' if is_trig else 'False'))
                startmode.append((eIndex, start_mode_str))
                bl_status.append((eIndex, bl_status_val))
                monitored.append((eIndex, mon_val))
            else:
                print("[WARN: Data Inconsistency] Key {} missing from dictionaries".format(key))

        result_handler.update({
            'DisplayName': displayname, 'Name': name, 'State': state, 
            'StartName': startname, 'StartMode': startmode, 'Trigger': trigger, 
            'BlocklistStatus': bl_status, 'monitored': monitored
        })
        print("[FINISH] Snippet Execution Successful. Processed {} services.".format(len(displayname)))

except Exception:
    error_msg = traceback.format_exc()
    print("[FATAL ERROR] Snippet failed at main level:\n{}".format(error_msg))
    self.internal_alerts.append((COLLECT_ERROR, "FATAL: Snippet failed. Traceback: {}".format(error_msg[:200])))
