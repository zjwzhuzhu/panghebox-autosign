"""胖盒云电脑 H5 自动签到包。"""
from .signin import (  # noqa: F401
    PangHeClient,
    CheckinError,
    load_credentials,
    parse_checkin_list,
    run_checkin,
)
