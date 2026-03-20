# Setting up Local ERP Sync

To sync your local Agility ERP data (Picks and Work Orders) with the Vercel cloud application, follow these steps on your local PC:

## 1. Prerequisites

### Install ODBC Driver
You must have the **ODBC Driver 17 for SQL Server** installed. The application uses this to connect to your `10.1.1.17` server.
- [Download from Microsoft](https://www.microsoft.com/en-us/download/details.aspx?id=56567) (Choose `msodbcsql.msi`)

### Install Python
Ensure Python 3.9+ is installed on your PC.

---

## 2. Setting Up the Project

1.  **Open Terminal**: Open PowerShell or Command Prompt in `C:\Users\amcgrean\python\tracker`.
2.  **Create Virtual Environment**:
    ```powershell
    python -m venv venv
    ```
3.  **Activate & Install**:
    ```powershell
    .\venv\Scripts\activate
    pip install -r requirements.txt
    ```

---

## 3. Configuration

Create or update the `.env` file in the root directory (`C:\Users\amcgrean\python\tracker\.env`) with the following:

```env
# Mirror database target
DATABASE_URL=postgresql://user:password@host:5432/postgres
```

---

## 4. Running the Sync

You can start the sync manually using the provided batch file:

1.  Double-click `run_sync.bat`.
2.  The console will open and show `Starting Local ERP Sync Service...`.
3.  Every 5 minutes, it will fetch local data and push it to the cloud.

> [!TIP]
> To keep this running 24/7, you can add `run_sync.bat` to your Windows **Task Scheduler** to start on system boot.
