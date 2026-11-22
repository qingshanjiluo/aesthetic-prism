grep -L "## 验收标准" docs/*.md > qa/evidence/S0/S0-02.log; test ! -s qa/evidence/S0/S0-02.log
