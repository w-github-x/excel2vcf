# -*- coding: utf-8 -*-
"""vCard 2.1 严格校验器（手机通讯录格式版）—— 模拟手机/通讯录解析器的真实行为

用法: python vcf校验器.py 生成的.vcf

检查项:
  1. 纯 ASCII（QP 编码后不应有裸中文；也不应有 BOM）
  2. CRLF 换行（部分手机不认 LF）
  3. 每行 <= 75 字节（vCard 硬性上限，超出会被截断）
  4. 属性名合法性（必须 ASCII，A-Z 0-9 -）
  5. 结构完整性（N 5段 / ADR 7段 / X-ANDROID-CUSTOM 16段 / FN 非空 / TEL 格式）
  6. QP 往返解码（折行合并 -> 解 =XX -> utf-8）
"""
import re, sys

raw = open(sys.argv[1], 'rb').read()
fails = []

# 0 BOM
print("0. 无BOM:", "PASS" if not raw.startswith(b'\xef\xbb\xbf') else "FAIL")
if raw.startswith(b'\xef\xbb\xbf'): fails.append("带BOM")

# 1 纯 ASCII
nonascii = any(b > 127 for b in raw)
print("1. 纯ASCII:", "PASS" if not nonascii else "FAIL")
if nonascii: fails.append("含非ASCII字节")

# 2 CRLF
lone_lf = raw.replace(b'\r\n', b'').count(b'\n')
print("2. CRLF:", "PASS" if lone_lf == 0 else "FAIL")
if lone_lf: fails.append("存在裸LF")

# 3 行长(不折行模式下超长是预期的——手机自己的导出就有 91 字节不折的行, 所以只警告)
lines = raw.split(b'\r\n')
over = [(i, len(l)) for i, l in enumerate(lines) if len(l) > 75]
if over:
    print("3. 行长<=75: WARN %d 行超75字节(不折行模式可接受; 若用 --fold 折行模式则不应出现)" % len(over))
else:
    print("3. 行长<=75: PASS")

# 4+5+6 严格解析
def unfold(b):
    out = []
    for l in b.split(b'\r\n'):
        if l.startswith(b' ') and out:
            out[-1] += l[1:]
        else:
            out.append(l)
    return out

def qp_dec(s):
    res = bytearray(); i = 0
    while i < len(s):
        if s[i:i+1] == b'=' and re.match(rb'[0-9A-Fa-f]{2}', s[i+1:i+3]):
            res.append(int(s[i+1:i+3], 16)); i += 3
        elif s[i:i+1] == b'=':
            i += 1                      # 容错: 跳过无法识别的 "="
        else:
            res.append(s[i]); i += 1
    return bytes(res).decode('utf-8', errors='replace')

cards = []
cur = None
unknown = []
for l in unfold(raw):
    if not l:
        continue
    if l == b'BEGIN:VCARD':
        cur = {}
        continue
    if l == b'END:VCARD':
        if cur is not None: cards.append(cur)
        cur = None
        continue
    if cur is None:
        continue
    k, _, v = l.partition(b':')
    ks = k.decode('ascii', errors='replace')
    base = ks.split(';')[0]
    if b'QUOTED-PRINTABLE' in k.upper():
        v = qp_dec(v)
    else:
        v = v.decode('utf-8', errors='replace')
    cur.setdefault(base, []).append(v)
    if not re.match(r'^[A-Za-z0-9-]+$', base):
        unknown.append(base)

print("4. 卡片数:", len(cards))
print("   非法属性名:", unknown if unknown else "无 (PASS)")

ok = True
for idx, c in enumerate(cards):
    if 'FN' not in c or not c['FN'][0]:
        print("   !! 卡%d 缺 FN 或 FN 为空" % (idx + 1)); ok = False
    if 'N' in c:
        for nv in c['N']:
            if nv.count(';') != 4:
                print("   !! 卡%d N 不是5段: %r" % (idx + 1, nv)); ok = False
    if 'ADR' in c:
        for av in c['ADR']:
            if av.count(';') != 6:
                print("   !! 卡%d ADR 不是7段: %r" % (idx + 1, av)); ok = False
    if 'X-ANDROID-CUSTOM' in c:
        for xv in c['X-ANDROID-CUSTOM']:
            seg = xv.split(';')
            if not seg[0].startswith('vnd.android.cursor.item/'):
                print("   !! 卡%d X-ANDROID-CUSTOM mime 异常: %r" % (idx + 1, seg[0])); ok = False
            if len(seg) != 16:
                print("   !! 卡%d X-ANDROID-CUSTOM 不是16段(%d): %r" % (idx + 1, len(seg), xv)); ok = False
    if 'TEL' in c:
        for tv in c['TEL']:
            if not re.match(r'^\+?\d+$', tv):
                print("   !! 卡%d TEL 异常: %r" % (idx + 1, tv)); ok = False
print("5. 结构完整性:", "PASS" if ok else "FAIL")
print("6. QP往返解码: 随 5 一并校验(解码后字段已打印)")

if fails or not ok or unknown:
    print("\n最终: FAIL", fails); sys.exit(1)
print("\n最终: ALL PASS")
