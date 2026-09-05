from ipdb._sources.dataplane import DataplaneSource

# Concatenation of three dataplane.org signal files (sshpwauth + telnetlogin +
# dnsrd), each with its own comment header — download() merges them into one
# file, and the `category` column disambiguates the signal per row.
_SAMPLE = (
    "# Dataplane.org - for operators, by operators\n"
    "# sshpwauth\n"
    "# 2026-07-28 12:00 - 2026-08-04 12:00\n"
    "#\n"
    "174          |  COGENT-174 - Cogent Communicat  |  149.13.96.133    |  2026-08-04 10:13:29  |  sshpwauth\n"
    "not-an-ip-row |  Bad AS  |  999.999.999.999  |  2026-08-04 10:00:00  |  sshpwauth\n"
    "# telnetlogin block\n"
    "5            |  SYMBOLICS - WFA Group LLC       |  201.216.86.55    |  2026-08-03 14:02:49  |  telnetlogin\n"
    "# dnsrd block\n"
    "174          |  COGENT-174 - Cogent Communicat  |  170.75.162.201   |  2026-07-31 19:52:41  |  dnsrd\n"
)


def test_dataplane_loads_three_signals_with_per_row_classification(tmp_path):
    (tmp_path / "dataplane.txt").write_text(_SAMPLE)
    s = DataplaneSource(data_dir=tmp_path)
    assert s.rebuild() == 3   # 3 valid IPs; malformed row + comments dropped

    ssh = s.query("149.13.96.133")[0]
    assert ssh["classification_type"] == "brute-force"
    assert ssh["native_categories"] == ["sshpwauth"]
    assert "native_type" not in ssh.get("extra", {})
    assert ssh["asn"] == 174
    assert ssh["as_name"] == "COGENT-174 - Cogent Communicat"
    assert ssh["last_seen"] == "2026-08-04 10:13:29"

    telnet = s.query("201.216.86.55")[0]
    assert telnet["classification_type"] == "brute-force"
    assert telnet["native_categories"] == ["telnetlogin"]
    assert "native_type" not in telnet.get("extra", {})

    dns = s.query("170.75.162.201")[0]
    assert dns["classification_type"] == "scanner"
    assert dns["native_categories"] == ["dnsrd"]
    assert "native_type" not in dns.get("extra", {})

    assert s.query("203.0.113.42") == {}   # not in feed


def test_dataplane_new_signal_categories_map(tmp_path):
    lines = "\n".join([
        "# test",
        "174 |  COGENT-174 - Cogent  |  154.3.40.77  |  2026-08-22 00:31:31  |  sipquery",
        "174 |  COGENT-174 - Cogent  |  154.3.40.78  |  2026-08-22 00:31:31  |  sipregistration",
        "174 |  COGENT-174 - Cogent  |  207.90.244.10  |  2026-08-22 14:39:14  |  smtpgreet",
    ])
    (tmp_path / "dataplane.txt").write_text(lines)
    s = DataplaneSource(data_dir=tmp_path)
    s.rebuild()
    assert s.query("154.3.40.77")[0]["classification_type"] == "brute-force"
    assert s.query("154.3.40.78")[0]["classification_type"] == "brute-force"
    assert s.query("207.90.244.10")[0]["classification_type"] == "scanner"
    assert s.query("154.3.40.77")[0]["native_categories"] == ["sipquery"]


def test_dataplane_signals_dict_has_eight_feeds():
    from ipdb._sources.dataplane import DataplaneSource
    assert set(DataplaneSource.SIGNALS) == {
        "sshpwauth", "telnetlogin", "dnsrd",
        "sipquery", "sipregistration", "smtpgreet",
        "smtpdata", "ntpmode7"}


def test_dataplane_smtpdata_spam_and_ntpmode7_scanner(tmp_path):
    """2026-09-05 修正( dataplane.org 文件头实证):ntpmode7 列的是
    "sending NTP mode 7 requests" 的源 IP——探测方(为找 DDoS 放大器而
    扫 monlist),非被探测的开放 NTP 服务(RSIT DDoS Amplifier 的定义
    对象)。改归 scanner/malicious(此前误读为 victim 侧反射器,归
    vulnerable-system/informational)。smtpdata 维持 spam:DATA = 实际
    投递报文体(非 EXPN/RCPT 探测),与 IntelMQ 官方 parser 的 scanner
    是有意分歧(数据头实测 "SMTP clients sending DATA commands")。"""
    lines = "\n".join([
        "# test",
        "2018 |  Tertiary Education  |  146.64.140.28  |  2026-09-04 09:04:07  |  smtpdata",
        "4134 |  CHINANET-BACKBONE  |  113.95.143.91  |  2026-08-31 06:33:52  |  ntpmode7",
        "5 |  SYMBOLICS - WFA  |  201.216.86.55  |  2026-08-03 14:02:49  |  telnetlogin",
    ])
    (tmp_path / "dataplane.txt").write_text(lines)
    s = DataplaneSource(data_dir=tmp_path)
    s.rebuild()
    smtp = s.query("146.64.140.28")[0]
    assert smtp["classification_type"] == "spam"
    assert smtp["verdict"] == "malicious"
    ntp = s.query("113.95.143.91")[0]
    assert ntp["classification_type"] == "scanner"
    assert ntp["verdict"] == "malicious"
    telnet = s.query("201.216.86.55")[0]
    assert telnet["classification_type"] == "brute-force"
    assert telnet["verdict"] == "malicious"
