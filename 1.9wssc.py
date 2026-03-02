try:
    import cPickle as pickle
except ImportError:
    import _pickle as pickle
import datetime
import sys
import unicodedata
import base64
import re

app_name = "Microsoft: Windows Server Service Configuration"
DO_REGEX = True


def get_last_cached_request_result(self, key, is_concurrent, pickling=True):
  
    collection_time = datetime.datetime.fromtimestamp(self.gmtime)
      
    # Increase the length of time cache data may be retrieved to 16 min
    #    5 min default time to live + 11 minute buffer added here
    expiration_buffer = datetime.timedelta(minutes=11)
    minimum_expire_time = collection_time - expiration_buffer
    
    if is_concurrent:
        query = """SELECT `key`, `value`, `date_updated`, `expires`
                   FROM `cache`.`dynamic_app`
                   WHERE `key` LIKE %s
                   AND `date_updated` <= %s
                   AND %s < `expires`
                   ORDER BY `date_updated` DESC
                   LIMIT 1"""
    else:
        # If not Concurrent PowerShell force a new collection if not
        # updated in the last 3 minutes
        updated_buffer = datetime.timedelta(minutes=3)
        minimum_expire_time = collection_time - updated_buffer
        query = """SELECT `key`, `value`, `date_updated`, `expires`
                   FROM `cache`.`dynamic_app`
                   WHERE `key` LIKE %s
                   AND `date_updated` <= %s
                   AND %s < `date_updated`
                   ORDER BY `date_updated` DESC
                   LIMIT 1"""

    arg = ("%" + key, collection_time, minimum_expire_time)
  
    self.dbc.execute(query, arg)
  
    result = self.dbc.fetchall()
  
    if len(result):
        key, result, cache_date_updated, cache_expires = result[0]
  
        self.logger.ui_debug('get_last_cached_request_result: Retrieved cache entry for key: {}, date updated: {}, expiration: {}'.format(key, cache_date_updated, cache_expires))
  
        if pickling:
            result = pickle.loads(result)
        return result
    else:
        self.logger.ui_debug('get_last_cached_request_result: No cache entry retrieved for key: {}'.format(key))
        return None

def concurrentps_enabled(self):
    powershell_service_flag = self.dbc.autofetch_value("""SELECT MAX(field_value+0) FROM
                                        master.system_custom_config WHERE field LIKE 'enable_powershell_service%'
                                        GROUP BY cug_filter ORDER BY cug_filter DESC LIMIT 1""")
    if powershell_service_flag is None:
        powershell_service_flag = 0
    else:
        powershell_service_flag = int(powershell_service_flag)
    self.logger.debug("Concurrent PowerShell Collector Service enabled: %s "
                              "(%s)", powershell_service_flag > 0, powershell_service_flag)
    return powershell_service_flag

def get_current_cached_request_result(self, req_guid, index_item=None):
    """
    This method is used by snippet applications to directly query cached results
    written by dynamic applications which utilize the SL1 built-in caching mechanism.
    
    However, rather than querying the cache with a key that includes an exact
    hour+minute combination, this method will return the most recent
    cache result which falls within the collection interval of the consumer application.
    If no result is found, a new collection by the cache producer is initiated.
    """
    req = self.dbc.autofetchrow_dict("select app_id, req_id from master.dynamic_app_requests where req_guid='%s'" %
                                     req_guid)

    cache_key = self.cache.generate_key(app_id=req['app_id'], did=self.did, use_timestamp=False, req_id=req['req_id'])
    self.logger.ui_debug('get_current_cached_request_result: Cache key: {}'.format(cache_key))
    
    is_concurrent = concurrentps_enabled(self)

    # Check cache if already have data for this polling interval.
    result = get_last_cached_request_result(self, cache_key, is_concurrent)

    if result is None and not is_concurrent:
        self.logger.ui_debug('get_current_cached_request_result: Cache miss, performing parent request')
        parent_sync_key = self.cache.generate_key(app_id=req['app_id'], did=self.did)
        cache_key = self.cache.generate_key(app_id=req['app_id'], req_id=req['req_id'], did=self.did)
        self.logger.ui_debug('get_current_cached_request_result: Updated cache key: {}'.format(cache_key))
        
        did = None
        if self.did != self.root_did:
            did = self.did
        self.collect_parent(cache_key, req['app_id'], parent_sync_key, did)
        result = self.cache.get(cache_key)

        if result:
            self.logger.ui_debug('get_current_cached_request_result: Parent request result successfully retrieved.')
        else:
            self.logger.ui_debug('get_current_cached_request_result: Parent request failed.')
            result = {}
    elif result is None:
        self.logger.ui_debug('get_current_cached_request_result: Cache miss!')
    else:
        self.logger.ui_debug('get_current_cached_request_result: Cache hit!')

    # Re-index according to index item
    if (result is not None) and (index_item is not None):
        index_mapping = result.get(index_item, {})
        for item in result:
            result[item] = {index_mapping.get(index, index): data for index, data in list(result[item].items())}

    return result


def get_block_list_services():
    # Get the blocklist
    sql = "SELECT service_name, did FROM master.definitions_service_autostart_exclude WHERE did in (0,{})".format(self.did)
    blocklist = self.dbc.autofetchall_dict(sql)  
    return blocklist
    
def is_service_on_blocklist(blocklist, serviceName, displayName):
    # look at the resultset known as blocklist to see if this service is in there
    bl_status_val = 0                                         # presume the service is not in the blocklist
    for service in blocklist:
        # if the service is in the blocklist
        try:
            if (service['service_name'] == serviceName or service['service_name'] == displayName or
               (DO_REGEX and (re.search(service['service_name'], serviceName) or re.search(service['service_name'], displayName)))):
                bl_status_val = 1                             # mark the service as blocklisted                             
                break   
        except Exception as e:
            self.logger.ui_debug('Regex format not supported "{}", generated error: {}'.format(service['service_name'], e))                    
    return bl_status_val


def service_encoding(text):
    result = None
    
    if isinstance(text, str):
       result = normalize_unicode(text)
    elif isinstance(text, bytes):
       if sys.version_info >= (3, 0):
            result = normalize_unicode(text.decode())
       else:
            result = normalize_unicode(text.decode("utf-8"))
    else:
       result = text
    return result

##
## silo.apps code
##    
def normalize_unicode(st):
   
    ascii_str = ""
    if sys.version_info >= (3, 0):
        for ch in st:
            ascii_ch = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            if ascii_ch == "":
                c = ch.encode("ascii", "backslashreplace")
                ascii_ch = "[" + c.decode() + "]"
            ascii_str += ascii_ch

        return ascii_str

    for ch in st:
        ascii_ch = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore")
        if ascii_ch == "":
            c = ch.encode("ascii", "backslashreplace")
            ascii_ch = "[" + c + "]"
        ascii_str += ascii_ch
    return ascii_str

def is_ascii(value):
    return all(ord(c) < 128 for c in value)

def replace_char(service):
    result = service
    for char in service:
        if not is_ascii(char):
            result = result.replace(char, '')
    return result

########################################

WINDOWS_SERVER_SERVICES_REQ_GUID = '828EFE6D4485860679972EACD7097ED1'
COLLECT_ERROR = 257
 
result = get_current_cached_request_result(self, WINDOWS_SERVER_SERVICES_REQ_GUID, "DisplayName")

# Get the data
try:
   
    data = result
    
    if data is None or not data:
        self.logger.ui_debug("Error: %s" % ("There are not data for services"))
        
    if data:
       
        # Couple of things to do:
        # 1) Get the blocklist of services we do not want to restart
        # 2) Rearrange the data returned from the powershell request into something
        #    that is digestable by the result handler.
    
        blocklist = get_block_list_services()    

        # Rearrange
        # First extract the individual dictionaries
        dn = data['DisplayName']
        n = data['Name']
        s = data['State']
        sn = data['StartName']
        sm = data['StartMode']
        trigger_val = data['Trigger']
    
        # These are the lists that will be plugged into result_handler['oid_name']
        displayname = []
        name = []
        state = []
        startname = []
        startmode = []
        bl_status = []
        trigger = []

        for key in list(dn.keys()):
            # look at the resultset known as blocklist to see if this service is in there
            serviceName = (base64.b64decode(n.get(key, ""))).decode("utf-8")
            bl_status_val = is_service_on_blocklist(blocklist, serviceName, key)
         
            if (key in s) and (key in n) and (key in sn) and (key in sm) and (key in trigger_val):
                eIndex = service_encoding(key)
                name_parsed = service_encoding(n[key])
                displayname_parsed = service_encoding(dn[key]) if is_ascii(dn[key]) else service_encoding(replace_char(dn[key]))
                startname_parsed = sn[key] if is_ascii(sn[key]) else replace_char(sn[key])

                displayname.append((eIndex, displayname_parsed))
                name.append((eIndex, name_parsed))
                state.append((eIndex, s[key]))
                startname.append((eIndex, startname_parsed))
                start_mode = sm[key]
                if trigger_val[key] == 'True':
                    start_mode += " (Trigger Start)"
                    trigger.append((eIndex, 'True'))
                else:
                    trigger.append((eIndex, 'False'))
                startmode.append((eIndex, start_mode))
                bl_status.append((eIndex, bl_status_val))
            else:
                self.internal_alerts.append((COLLECT_ERROR, "[%s] for device %s [%s] IP: %s Error: Data Inconsistency in PowerShell results" % (self.app_id, self.name, self.did, self.ip)))
                
        # very good, return the transformed data
        result_handler['DisplayName'] = displayname
        result_handler['Name'] = name
        result_handler['State'] = state
        result_handler['StartName'] = startname
        result_handler['StartMode'] = startmode
        result_handler['Trigger'] = trigger
        result_handler['BlocklistStatus'] = bl_status
except AttributeError:
    pass
except Exception as err:
    self.logger.exception('unhanled error')
    self.internal_alerts.append((COLLECT_ERROR, "%s [%s] for device %s [%s] IP: %s Error: %s" % (app_name, self.app_id, self.name, self.did, self.ip, err)))