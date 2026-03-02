# 🚀 ScienceLogic PowerPack: Windows Server Service Configuration (WSSC)

Enhancing Windows Service monitoring with intelligent filtering, advanced metadata, and internationalization support.

---

## 🛠️ Key Changes Implemented

We have integrated custom business logic into the modern **1.9 framework**, ensuring high performance while maintaining critical monitoring rules.

1.  **🔍 Hardcoded Exclusion List**  
    Added `exclude_services_list` (containing services like `AmazonSSMAgent`, `NetBackup`, etc.) to the top of the file for quick management.
2.  **⏱️ Delayed Start Detection**  
    The script now pulls `DelayedAutostart` status from cached parent data, providing deeper insight into service startup behavior.
3.  **🏷️ Enhanced StartMode Labels**  
    The StartMode OID accurately reflects complex states:
    *   `Automatic (Delayed Start, Trigger Start)`
    *   `Automatic (Delayed Start)`
4.  **⚖️ Monitored Status Logic**
    *   **🔴 Monitored = No:** If the service is Trigger-start, Delayed-start, or on the hardcoded exclusion list.
    *   **🟢 Monitored = Yes:** If it is a standard Auto-start service that *should* be running.
5.  **📊 Output Registration**  
    Added the `monitored` OID to the `result_handler` for precise alerting in ScienceLogic SL1.

---

## 🏗️ Version Comparison

| Feature | v1.2 (Legacy) | v1.1 (Customized) | v1.9 (Modern Default) | **v1.9 (Integrated)** |
| :--- | :---: | :---: | :---: | :---: |
| **Protocol** | WMI/DCOM | WMI/DCOM | PowerShell Cache | **PowerShell Cache** |
| **Python 3 Support** | ❌ | ❌ | ✅ | ✅ |
| **Trigger/Delayed Start** | ❌ | ✅ | ❌ | ✅ |
| **Regex Exclusions** | ❌ | ✅ | ❌ | ✅ |
| **Unicode/Diacritics** | ❌ | ✅ | ❌ | ✅ |
| **Performance** | Low | Low | High | **High** |

---

## ✨ Developer-Added Features

### 1. 🔊 Noise Reduction Logic (Trigger & Delayed Start)
*   **The Problem:** ScienceLogic usually alerts if an "Auto" service is stopped. This causes thousands of false alarms for services like `MapsBroker` that only start when triggered.
*   **The Solution:** Integrated registry checks for `TriggerInfo` and `DelayedAutostart`.
*   **Impact:** Prevents "Service Down" alerts for services intended to be stopped until needed.

### 2. 🗄️ Custom Database Blacklist
*   **The Solution:** Integration with SQL table `master.definitions_service_autostart_exclude`.
*   **Flexibility:** 
    *   **Global Exclusions:** (`did = 0`) Ignore a service across the entire enterprise.
    *   **Device-Specific:** (`did = self.did`) Ignore a service on a specific server only.

### 3. ⚰️ Hardcoded "Service Graveyard"
A manually curated list of noisy enterprise services automatically ignored:
*   `AmazonSSMAgent`: Frequently cycles.
*   `NetBackup`: Only runs during backup windows.
*   `SeOS Agent`: Managed via external security tools.

### 4. 🌐 Internationalization (Diacritic Support)
*   **The Problem:** Non-English characters (ö, é, ñ) can crash scripts or fail matching.
*   **The Solution:** A sophisticated `Normalization` function strips accents (e.g., `Ménage` → `Menage`).
*   **Impact:** Consistent monitoring across global, multi-lingual server environments.

### 5. 🧬 Advanced Regex Matching
*   **The Solution:** Switched from "Equal To" to **Regular Expression** matching.
*   **Impact:** Allows excluding multiple services with one line (e.g., `Esa.*` or any service containing `.NET`).

### 6. 🛡️ Unicode Safety Net
*   **The Change:** Integration of `silo_apps.unicode_handler`.
*   **Impact:** Prevents Dynamic Application failure if a single service has a corrupted or unusual character name.

---

## 📝 Summary of Integration

The core task was to "port" these improvements from the old **1.1 customized version** into the high-performance **1.9 framework**. 

*   **Logic:** Re-introduced the intelligent `Monitored` OID.
*   **Matching:** Integrated advanced Regex-based exclusion matching.
*   **Metadata:** Improved `StartMode` strings for better operator visibility.
*   **Compatibility:** Fully compatible with both **Python 2** and **Python 3**.

---
*Created for ScienceLogic PowerPack Optimization*
