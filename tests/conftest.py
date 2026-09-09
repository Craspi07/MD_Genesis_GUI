import os

# Run Qt headless in test/CI environments unless a real display is set.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
