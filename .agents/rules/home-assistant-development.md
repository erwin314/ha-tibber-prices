---
trigger: always_on
---

# Home Assistant Development Rules

**Trigger:** Apply these rules whenever the user asks to write, debug, or refactor a Home Assistant integration, component, or configuration.

**Workflow:**
1. **Do not guess:** Home Assistant APIs change frequently. Do not rely solely on your baseline training data for `hass` object methods, config flows, or entity structures.
2. **Search first:** Before generating code, use your file-search tools to query the local documentation in the `/docs/ha-dev/` directory. 
3. **Targeted reading:** If you are building a specific component (e.g., a config flow), read the specific markdown files related to that component (e.g., `/docs/ha-dev/config_entries_index.md`) to get the exact syntax and requirements.
4. **Implementation:** Write the code strictly adhering to the architectural guidelines and examples found in those local markdown files.