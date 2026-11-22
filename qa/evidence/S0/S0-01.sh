n=$(ls docs/*.md 2>/dev/null | wc -l); echo "docs count=$n" | tee qa/evidence/S0/S0-01.log; test "$n" -ge 9
