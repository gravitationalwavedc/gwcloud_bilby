#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    # Mock gwosc event resolution during testing to avoid network timeouts
    if "test" in sys.argv:

        class MockDatasets:
            @staticmethod
            def event_gps(event):
                event_map = {
                    "GW150914": 1126259462.0,
                    "GW151226": 1135136350.0,
                }
                if event in event_map:
                    return event_map[event]
                raise ValueError(f"Unknown event {event}")

        sys.modules["gwosc.datasets"] = MockDatasets

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gw_bilby.development-settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
