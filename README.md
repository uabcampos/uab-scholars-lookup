# UAB Scholars Lookup

Thin Python client for the [Scholars@UAB](https://scholars.uab.edu/) REST API.

```bash
pip install uab-scholars-lookup   # soon on PyPI

# Search by name
uab-scholars search "Andrea Cherrington"

# List faculty in Preventive Medicine
uab-scholars department "Med - Preventive Medicine" --max 10
```

See `UAB_Scholars_API_README.md` for full endpoint docs and advanced filter payloads.

---

## Development

```bash
git clone https://github.com/your-org/uab-scholars-lookup && cd uab-scholars-lookup
python -m venv venv && source venv/bin/activate
pip install -e .[cli] -r requirements-dev.txt
pytest
```
