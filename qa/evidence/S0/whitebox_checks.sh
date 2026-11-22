echo '=== 00_PRD self-check #1 ==='
grep -qE '^\| M0 \| 段0 \| 0% \|' docs/00_PRD.md && grep -qE '^\| M1 \| 段1 \| 25% \|' docs/00_PRD.md && grep -qE '^\| M2 \| 段2 \| 50% \|' docs/00_PRD.md && grep -qE '^\| M3 \| 段3 \| 75% \|' docs/00_PRD.md && grep -qE '^\| M4 \| 段4 \| 100% \|' docs/00_PRD.md && grep -qE '^\| M5 \| 段5 \| 125% \|' docs/00_PRD.md && grep -qE '^\| M6 \| 段6 \| 150% \|' docs/00_PRD.md && grep -qE '^\| M7 \| 段7 \| 175% \|' docs/00_PRD.md && grep -qE '^\| M8 \| 段8 \| 200% \|' docs/00_PRD.md
echo "exit=$?"
echo '=== 00_PRD self-check #2 ==='
test $(grep -cE '^AC[1-9]' docs/00_PRD.md) -eq 9 && test $(grep -c 'sh -c "' docs/00_PRD.md) -ge 9
echo "exit=$? ac=$(grep -cE '^AC[1-9]' docs/00_PRD.md) cmd=$(grep -c 'sh -c "' docs/00_PRD.md)"
echo '=== 00_PRD self-check #3 ==='
grep -q '六字段' docs/00_PRD.md && grep -q 'P50 ≤ 150 ms' docs/00_PRD.md && grep -q 'P95 ≤ 500 ms' docs/00_PRD.md && grep -q 'Pearson r ≥ 0.70' docs/00_PRD.md && grep -q '主动学习采样脚本' docs/00_PRD.md && grep -q '版本管理' docs/00_PRD.md && grep -q '已知限制 ≥5 条' docs/00_PRD.md && grep -q 'US5.*段2' docs/00_PRD.md
echo "exit=$?"
echo '=== 00_PRD self-check #4 ==='
grep -qE '七.{0}键' docs/00_PRD.md; a=$?; grep -qE 'seg[0-9]' docs/00_PRD.md; b=$?; c=$(grep -c 'qa/evidence/S[0-8]/' docs/00_PRD.md); test $a -ne 0 && test $b -ne 0 && test $c -ge 9
echo "exit=$? seg_hits=$((1-a)) legacy=$((1-b)) evid=$c"
echo '=== C-BRANCH-01 self-check #3 ==='
for k in '(N,32,56,56)' '(N,128,14,14)'; do
  grep -qF "$k" docs/01_ARCH.md || { echo "FAIL-arch $k"; exit 1; }
  grep -qF "${k/, /,}" docs/contracts/model_branch_interfaces.md || grep -qF "${k/(\(/(}" docs/contracts/model_branch_interfaces.md || { echo "FAIL-contract $k"; exit 1; }
done
echo "exit=$?"
echo '=== shape literals ==='
grep -cF '(N, 32, 56, 56)' docs/contracts/model_branch_interfaces.md
grep -cF '(N,32,56,56)' docs/01_ARCH.md
grep -cF '(N, 128, 14, 14)' docs/contracts/model_branch_interfaces.md
grep -cF '(N,128,14,14)' docs/01_ARCH.md
echo '=== teacher width conflict ==='
grep -n '分支宽度 96' docs/01_ARCH.md
grep -n 'D=64 教师' docs/contracts/model_branch_interfaces.md
grep -n '256→4' docs/01_ARCH.md
echo '=== assets/sample.png existence ==='
test -f assets/sample.png && echo present || echo MISSING
grep -rn 'assets/sample.png' docs/00_PRD.md | head -3
