# -*- coding: utf-8 -*-
"""获取 CSI300/500/1000 成分股列表(akshare),合并去重后保存到文件。"""
import os
import json
import akshare as ak

INDICES = (('000300', 'csi300'), ('000905', 'csi500'), ('000852', 'csi1000'))

all_codes = {}          # code -> set of index names
for idx, key in INDICES:
    df = ak.index_stock_cons_csindex(symbol=idx)
    col = '成分券代码'
    codes = [str(x).zfill(6) for x in df[col].tolist()]
    print(f'{key}: {len(codes)} 只')
    for c in codes:
        all_codes.setdefault(c, set()).add(key)

# 合并后的去重列表
union = sorted(all_codes.keys())
print(f'合并去重后: {len(union)} 只')
print(f'沪深300 独立: {sum(1 for c in all_codes if all_codes[c] == {"csi300"})}')
print(f'中证500 独立: {sum(1 for c in all_codes if all_codes[c] == {"csi500"})}')
print(f'中证1000 独立: {sum(1 for c in all_codes if all_codes[c] == {"csi1000"})}')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'csi_universe.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump({'union': union, 'members': {c: sorted(v) for c, v in all_codes.items()}},
              f, ensure_ascii=False, indent=1)
print(f'saved -> {out}')
print('sample:', union[:10])
