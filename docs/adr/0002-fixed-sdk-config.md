# Device SDK Type is Fixed After Initial Configuration

The type of SDK Provider (vivo, OPPO, etc.) connected to a device is configured once during setup and does not change during the device's lifetime. If a device has no SDK Provider, it uses A11Y exclusively. Cloud backend does not need to handle mid-session SDK switching.

This differs from the original plan which suggested dynamic SDK discovery. The simplified design assumes device SDK configuration is stable.
