"""胖盒云电脑 H5 自动签到。

凭据来源：H5 页面 localStorage。
  key `fufuhub_user`  = {"userInfo":{...},"token":"<JWT>"}
  key `globalState`   = {"uid":<n>,"uuid":"<machine-uuid>","flowid":"..."}

接口（H5 代理，无签名校验，6 个固定头）：
  POST /v1/nika/client/getcheckinlist   body {uid}
  POST /v1/nika/client/checkinprize     body {uid, prize_id}

业务码：
  3584316 = 今日已签到
  3584901 = token 失效
"""
import io
import json
import os
import sys


def _ensure_utf8_stdout():
    """Windows 控制台默认 GBK，重定向到文件时中文会乱码；仅在编码不足时包一层。

    不能无条件重建 sys.stdout：解释器退出时会关闭原缓冲区，
    导致 print 抛 "I/O operation on closed file"。
    """
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') >= 'utf8':
            return
    except (AttributeError, TypeError):
        pass
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


_ensure_utf8_stdout()

import requests  # noqa: E402

BASE_URL = os.environ.get('PANGHEBOX_BASE_URL', 'https://panghebox.com/mp/cgame/api')
ACCESS_KEY = os.environ.get('PANGHEBOX_ACCESS_KEY', '90f8699a-e0d9-4ed2-8796-4ad2af58c27c')
VERSION = os.environ.get('PANGHEBOX_VERSION', '1.8.0')
PLATFORM = os.environ.get('PANGHEBOX_PLATFORM', 'h5-web')

CODE_ALREADY_DONE = 3584316
CODE_TOKEN_INVALID = 3584901


class CheckinError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def load_credentials():
    """从环境变量读取凭据。

    PANGHEBOX_CREDENTIALS 接受两种形式：
      1) fufuhub_user 的 JSON 原文（含 userInfo.token）
      2) 完整 JSON：{"token":"...","uid":N,"uuid":"..."}
    也可以分别用 PANGHEBOX_TOKEN / PANGHEBOX_UID / PANGHEBOX_UUID。
    """
    raw = os.environ.get('PANGHEBOX_CREDENTIALS', '').strip()
    token = os.environ.get('PANGHEBOX_TOKEN', '').strip()
    uid = os.environ.get('PANGHEBOX_UID', '').strip()
    uuid = os.environ.get('PANGHEBOX_UUID', '').strip()

    if raw:
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as e:
            raise CheckinError(-1, 'PANGHEBOX_CREDENTIALS 不是合法 JSON: %s' % e)
        if not isinstance(d, dict):
            raise CheckinError(-1, 'PANGHEBOX_CREDENTIALS 应为 JSON 对象')
        if not token:
            token = str(d.get('token') or (d.get('userInfo') or {}).get('token') or '')
        if not uid:
            uid = str(d.get('uid') or (d.get('userInfo') or {}).get('uid') or '')
        if not uuid:
            uuid = str(d.get('uuid') or (d.get('userInfo') or {}).get('uuid') or '')

    if not token:
        raise CheckinError(-1, '缺少 token（PANGHEBOX_CREDENTIALS 或 PANGHEBOX_TOKEN）')
    if not uid:
        raise CheckinError(-1, '缺少 uid（PANGHEBOX_CREDENTIALS 或 PANGHEBOX_UID）')

    return {'token': token.strip(), 'uid': uid.strip(), 'uuid': uuid.strip()}


class PangHeClient:
    def __init__(self, cred):
        self.cred = cred
        self.session = requests.Session()

    def headers(self):
        h = {
            'User-Agent': ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                           'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
                           'Mobile/15E148 Safari/604.1'),
            'Origin': 'https://panghebox.com',
            'Referer': 'https://panghebox.com/mp/cgame/me/signin',
            'Version': VERSION,
            'Accesskey': ACCESS_KEY,
            'Platform': PLATFORM,
            'Content-Type': 'application/json',
        }
        if self.cred.get('token'):
            h['Authorization'] = self.cred['token']
        if self.cred.get('uuid'):
            h['Machineid'] = self.cred['uuid']
        return h

    def request(self, path, payload):
        url = BASE_URL.rstrip('/') + path
        r = self.session.post(url, headers=self.headers(), json=payload, timeout=30)
        try:
            d = r.json()
        except Exception:
            raise CheckinError(-1, '响应非 JSON: HTTP %s %s' % (r.status_code, r.text[:300]))
        ret = d.get('ret') or {}
        code = ret.get('code')
        if code != 0:
            raise CheckinError(code, ret.get('msg') or 'unknown error')
        return d.get('body')

    def get_checkin_list(self):
        return self.request('/v1/nika/client/getcheckinlist', {'uid': int(self.cred['uid'])})

    def checkin_prize(self, prize_id):
        return self.request('/v1/nika/client/checkinprize',
                            {'uid': int(self.cred['uid']), 'prize_id': prize_id})


def parse_checkin_list(body):
    """把 getcheckinlist 的 body 整理成 [{day, prize_id, prize_name, minutes, signed, can_sign}]"""
    out = []
    if not isinstance(body, dict):
        return out
    lst = body.get('checkin_list') or []
    for i, item in enumerate(lst, start=1):
        if not isinstance(item, dict):
            continue
        prize_id = item.get('prize_id')
        if prize_id is None:
            prize_id = item.get('prize_sec_id')
        minutes = None
        sale = item.get('sale_info') or []
        for s in sale:
            if isinstance(s, dict) and s.get('sale_type') == 101:
                minutes = s.get('sale_value')
                break
        out.append({
            'day': item.get('date') or i,
            'prize_id': prize_id,
            'prize_name': item.get('prize_name'),
            'minutes': minutes,
            'signed': bool(item.get('is_sign') or item.get('signed')),
            'can_sign': bool(item.get('can_sign') or item.get('canSign')),
            'raw': item,
        })
    return out


def describe_reward(item):
    if item.get('minutes') is not None:
        return '%s 分钟时长卡' % item['minutes']
    for s in (item.get('raw', {}).get('sale_info') or []):
        if isinstance(s, dict):
            st = s.get('sale_type')
            sv = s.get('sale_value')
            if st == 1:
                return '%s 盒币' % sv
            if st == 101:
                return '%s 分钟时长卡' % sv
            return 'sale_type=%s value=%s' % (st, sv)
    return item.get('prize_name') or '未知奖励'


def run_checkin():
    cred = load_credentials()
    client = PangHeClient(cred)
    print('uid=%s uuid=%s' % (cred['uid'], (cred['uuid'] or '(空)')[:8] + '...'))

    body = client.get_checkin_list()
    days = parse_checkin_list(body)
    count = (body or {}).get('checkin_count')
    print('签到状态: 已签 %s 天，周期共 %s 天' % (count, len(days)))
    for d in days:
        flag = '已签' if d['signed'] else ('可签' if d['can_sign'] else '未开放')
        print('  第%s天: %-14s [%s] prize_id=%s' % (d['day'], describe_reward(d), flag, d['prize_id']))

    signed = [d for d in days if d['signed']]
    if signed:
        print('今日已签到，无需重复操作。')
        return 0

    target = None
    for d in days:
        if d['can_sign'] and d['prize_id'] is not None:
            target = d
            break
    if target is None:
        # 没有 can_sign 标记时，取第一个未签的项
        for d in days:
            if not d['signed'] and d['prize_id'] is not None:
                target = d
                break
    if target is None:
        print('没有找到可领取的奖励项。')
        return 1

    print('领取第%s天奖励: %s (prize_id=%s)' % (target['day'], describe_reward(target), target['prize_id']))
    res = client.checkin_prize(target['prize_id'])
    print('签到接口响应: %s' % json.dumps(res, ensure_ascii=False)[:500])
    print('✅ 签到成功，获得 %s' % describe_reward(target))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(run_checkin())
    except CheckinError as e:
        if e.code == CODE_ALREADY_DONE:
            print('今日已签到（code %s），跳过。' % e.code)
            sys.exit(0)
        if e.code == CODE_TOKEN_INVALID:
            print('❌ token 已失效（code %s），需要重新登录获取凭据。' % e.code)
        else:
            print('❌ 失败: code=%s msg=%s' % (e.code, e.msg))
        sys.exit(1)
