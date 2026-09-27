# City Bike System sandbox

This sandbox application is focused on the backend serving [City Bike System](https://citibikenyc.com/system-data) data.

## Data ingestion

The data ingestion is implemented with Meltano ELT tool.

### Ingestion initialization steps

Don't run these commands. This is how the meltano project has been initialized.

The project has been setup with uv

```powershell
  uv init
  uv sync
  .\.venv\Scripts\activate.ps1
```

Note! Non documented capability. To avoid global Meltano installation, used non documented command:

```powershell
  uv add --dev meltano
```

Cookiecutter is used to create custom extractors:
```powershell
  uv add --dev cookiecutter
```

Initialize meltano project

```powershell
  meltano init meltano
```

### Bootstrap

Install uv:

```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/0.12.19/install.ps1 | iex"
```

Install dependencies and activate environment:

```powershell
  uv sync
  .\.venv\Scripts\activate.ps1
```
