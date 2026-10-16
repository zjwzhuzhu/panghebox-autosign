import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from panghebox_autosign.signin import run_checkin

if __name__ == '__main__':
    sys.exit(run_checkin())
