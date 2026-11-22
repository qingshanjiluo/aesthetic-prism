# q2 补验：A) 8 行 assert 真验（纯 python，零引号穿透）  B) identical 对定位  C) 07_PLAN 段2 产物存在性
echo '=== A) 8 行三参 assert 真验（最终版，AST 级）==='
python qa/evidence/S2/wb2_assert.py
echo "A_EXIT=$?"
echo '=== B) identical 2 对定位 ==='
python qa/evidence/S2/wb2_identical.py
echo "B_EXIT=$?"
echo '=== C) 07_PLAN 段2 产物存在性 ==='
python qa/evidence/S2/wb2_artifacts.py
echo "C_EXIT=$?"
