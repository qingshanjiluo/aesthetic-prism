echo '=== A. contract unspaced shape literal ==='
grep -cF '(N,32,56,56)' docs/contracts/model_branch_interfaces.md || true
grep -cF '(N,128,14,14)' docs/contracts/model_branch_interfaces.md || true
echo '=== B. 06_RISK mitigation carriers in 08/07 ==='
for x in label_quality.json test_license_whitelist.py holdout; do
  a=$(grep -c "$x" docs/08_ACCEPTANCE.md || true)
  b=$(grep -c "$x" docs/07_PLAN.md || true)
  c=$(grep -rc "$x" docs/02_DATA.md docs/03_TRAINING.md docs/contracts/dataset_DatasetSample.md 2>/dev/null | tr '\n' ' ')
  echo "$x  08=$a 07=$b others=[$c]"
done
echo '=== C. 06_RISK self-checks ==='
for r in R1 R2 R3 R4 R5; do grep -q "### $r " docs/06_RISK.md || echo "MISS-$r"; done
test $(grep -c '^| 缓解·事前 |' docs/06_RISK.md) -eq 5 && test $(grep -c '^| 缓解·事后 |' docs/06_RISK.md) -eq 5 && test $(grep -c '^| 责任方 |' docs/06_RISK.md) -eq 5 && echo SC1-PASS || echo SC1-FAIL
for k in 数据偏差 过拟合 标注噪声 性能不达标 版权风险; do grep -q "$k" docs/06_RISK.md || echo "MISS-$k"; done
test $(grep -c '^| 触发信号 |' docs/06_RISK.md) -eq 5 && grep -q '^## 2. 风险矩阵汇总' docs/06_RISK.md && echo SC3-PASS || echo SC3-FAIL
test $(grep -cE '^\| R[1-5] \|' docs/06_RISK.md) -eq 5 && echo SC4-PASS || echo SC4-FAIL
echo '=== D. R3 median attribution cross-check ==='
grep -n '中位数' docs/06_RISK.md docs/contracts/dataset_DatasetSample.md docs/04_LABELING.md | head -8
echo '=== E. teacher width cross-doc ==='
grep -n '96' docs/01_ARCH.md docs/contracts/model_branch_interfaces.md docs/06_RISK.md | grep -i '宽\|D=\|width\|分支' || true
echo '=== F. gate segment cross-doc ==='
grep -n '段4' docs/01_ARCH.md | head -5
grep -n 'S6-01' docs/08_ACCEPTANCE.md | head -2
