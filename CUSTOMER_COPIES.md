# Customer Copies — Phone Reseller CRM v2.3

Three builds — pick the folder that matches your computer.

| Folder | Platform | Who should use it |
|--------|----------|-------------------|
| **Customer Copy Apple Silicon** | Mac M1 / M2 / M3 / M4 | Apple Silicon Macs only |
| **Customer Copy Intel Mac** | Mac Intel (Core i5/i7) | Older Intel MacBooks / iMacs |
| **Customer Windows Copy** | Windows 10/11 | Windows PCs |

## Quick start

### Mac (Apple Silicon — M chip)
1. Open folder `Customer Copy Apple Silicon`
2. If blocked: Terminal → `xattr -cr "Phone Reseller CRM.app"`
3. Double-click **Phone Reseller CRM.app**
4. Browser → http://localhost:5050

### Mac (Intel chip)
1. Open folder `Customer Copy Intel Mac`
2. Same steps as above

### Windows
1. Open folder `Customer Windows Copy`
2. Double-click **Phone Reseller CRM\Phone Reseller CRM.exe**
3. Browser → http://localhost:5050

## Wrong chip error?

If Mac says *"can't open, not supported on this Mac"*:
- **Intel Mac** → you opened the **Apple Silicon** folder by mistake → use **Customer Copy Intel Mac**
- **M chip Mac** → you opened the **Intel** folder → use **Customer Copy Apple Silicon**

## Rebuild (developers)

```bash
cd Source
# Mac Apple Silicon (on M Mac or CI arm64 job)
python3 build_customer_mac.py --arch arm64

# Mac Intel (on Intel Mac, or CI with x64 Python)
python3 build_customer_mac.py --arch x86_64

# Windows (on Windows only)
python build_customer_windows_copy.py
```

GitHub Actions builds all three on push to `MoreFixes-update`.
