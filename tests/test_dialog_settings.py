from pathlib import Path

from app.settings import Settings
from app.wsl import WslBridge
from ui.dialog_settings import SettingsDialog, HealthCheckWorker

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def test_dialog_prefills_from_settings():
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    settings.linux_user = "biplab"
    settings.mpi_extra_args = "--mca btl vader,self"
    settings.vmd_path = r"C:\VMD 2.0.0a6\vmd.exe"

    dialog = SettingsDialog(settings)
    assert dialog.distro_combo.currentText() == "Ubuntu-24.04"
    assert dialog.user_edit.text() == "biplab"
    assert dialog.mpi_args_edit.text() == "--mca btl vader,self"
    assert dialog.vmd_path_edit.text() == r"C:\VMD 2.0.0a6\vmd.exe"


def test_dialog_save_persists_vmd_path():
    settings = Settings()
    dialog = SettingsDialog(settings)
    dialog.vmd_path_edit.setText(r"D:\Tools\VMD\vmd.exe")
    dialog._on_save()
    assert settings.vmd_path == r"D:\Tools\VMD\vmd.exe"


def test_health_check_worker_emits_items():
    bridge = WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)
    worker = HealthCheckWorker(bridge)
    results = {}
    worker.finished.connect(lambda items: results.__setitem__("items", items))
    worker.run()
    assert "items" in results
    assert len(results["items"]) > 0
