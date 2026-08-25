"""İsteğe bağlı analizler ve tarama limitleri için tek yapılandırma kaynağı."""
from dataclasses import dataclass
import os


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, "1" if default else "0") == "1"


@dataclass(frozen=True)
class ApplicationSettings:
    pro_kap: bool = True
    pro_faaliyet: bool = False
    pro_temettu: bool = False
    pro_analiz_limit: int = 100
    kap_analiz_limit: int = 10
    faaliyet_analiz_limit: int = 10
    gecelik_momentum_status: str = "experimental"

    @classmethod
    def from_env(cls) -> "ApplicationSettings":
        return cls(pro_kap=_flag("PRO_KAP", True), pro_faaliyet=_flag("PRO_FAALIYET", False),
                   pro_temettu=_flag("PRO_TEMETTU", False),
                   pro_analiz_limit=int(os.environ.get("PRO_ANALIZ_LIMIT", os.environ.get("KAP_ANALIZ_LIMIT", "100"))),
                   kap_analiz_limit=max(1, int(os.environ.get("KAP_ANALIZ_LIMIT", "10"))),
                   faaliyet_analiz_limit=int(os.environ.get("FAALIYET_ANALIZ_LIMIT", "10")))


SETTINGS = ApplicationSettings.from_env()
