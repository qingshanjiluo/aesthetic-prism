set -e
{
echo "== S8-00.version evidence =="
date -u +%Y-%m-%dT%H:%M:%SZ
echo "reports/versioning.md exists: $(test -f reports/versioning.md && echo yes || echo no)"
echo "git repo: $(git rev-parse --is-inside-work-tree 2>&1 || echo not-a-git-repo)"
echo "--- reports/versioning.md head ---"
head -5 reports/versioning.md
} >> qa/evidence/S8/S8-00.version.log 2>&1
tail -12 qa/evidence/S8/S8-00.version.log
