# Container App Monitor for Home Assistant

**Container App Monitor** is a custom Home Assistant integration designed for **Home Assistant OS (HAOS)** and **Supervised** installations. It monitors your add-on container apps and automatically creates interactive Home Assistant **Repair Issues** if a container drifts from its expected state (e.g., an "always-on" app stops running, or an app that should stay off starts running).

---

## Features

* **HACS Compatible:** Easily install and update via HACS as a custom repository.
* **Supervisor REST API Integration:** Communicates natively with the Home Assistant Supervisor to inspect add-on states, fetch container logs, and execute start/stop commands.
* **Interactive Repairs Flow:** When a state mismatch is detected, a repair issue is created. Clicking "Fix" displays the most recent container logs and prompts you for confirmation before starting or stopping the app.
* **Self-Healing / Automatic Dismissal:** If you manually start or stop a container app outside of the repair flow, the integration detects the correction during its next poll and automatically clears the repair issue.
* **UI Configured:** Easily select your installed container apps and set their expected state (`running` or `not running`) directly from the Home Assistant UI.

---

## Installation

### Via HACS (Recommended)
1. Open **HACS** in your Home Assistant instance.
2. Click on the three dots in the top right corner and select **Custom repositories**.
3. Paste your repository URL and select **Integration** as the category.
4. Click **Add**, then find **Container App Monitor** in the HACS store and click **Download**.
5. Restart Home Assistant.

### Manual Installation
1. Copy the `container_app_monitor` folder into your `<config-dir>/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

1. Go to **Settings** > **Devices & Services** > **Integrations**.
2. Click **Add Integration** and search for **Container App Monitor**.
3. Choose the container app you wish to monitor from the dropdown list of installed add-ons.
4. Select your **Expected State**:
   * **`running`**: Triggers a repair issue if the app stops. The repair flow will offer to **start** it.
   * **`not running`**: Triggers a repair issue if the app starts. The repair flow will offer to **stop** it.
5. Click **Submit**.

---

## How It Works

* **Polling:** Every 30 seconds, the integration queries the local Supervisor API (`http://supervisor/`) to verify the state of your configured container apps.
* **Issue Creation:** If the runtime state doesn't match your configuration, Home Assistant's native issue registry raises an alert.
* **Remediation:** Opening the repair dialog pulls the last 50 lines of stdout from the container app's logs to help you diagnose why it failed before confirming the remediation action.