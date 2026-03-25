#!/bin/bash
# ═══════════════════════════════════════════════════════════
# FAC v14 Compatibility Fix
# Run after installing FAC v2.3+ on Frappe v14
# 
# Usage: bash fac_v14_compat.sh /path/to/frappe-bench
# 
# What it does:
#   - Fixes frappe.cache. → frappe.cache(). (v14 requires function call)
#   - Fixes site_cache(ttl=...) → site_cache() (v14 doesn't support ttl)
#   - Safe to run multiple times (idempotent)
#
# GitHub: https://github.com/kulharir7/niv_ai/scripts/fac_v14_compat.sh
# ═══════════════════════════════════════════════════════════

set -e

BENCH_PATH="${1:-/home/gws/frappe-bench}"
FAC_PATH="$BENCH_PATH/apps/frappe_assistant_core"

if [ ! -d "$FAC_PATH" ]; then
    echo "ERROR: FAC not found at $FAC_PATH"
    echo "Usage: bash fac_v14_compat.sh /path/to/frappe-bench"
    exit 1
fi

echo "═══ FAC v14 Compatibility Fix ═══"
echo "FAC path: $FAC_PATH"

# Check Frappe version
FRAPPE_VERSION=$(python3 -c "import frappe; print(frappe.__version__)" 2>/dev/null || echo "unknown")
echo "Frappe version: $FRAPPE_VERSION"

# Step 1: Fix frappe.cache. → frappe.cache().
echo ""
echo "Step 1: Fixing frappe.cache → frappe.cache()..."

METHODS="get_value set_value delete_value delete_key delete_keys hdel hget hset redis"

for method in $METHODS; do
    find "$FAC_PATH/frappe_assistant_core/" -name "*.py" -not -path "*__pycache__*" \
        -exec sed -i "s/frappe\.cache\.${method}/frappe.cache().${method}/g" {} \;
done

# Fix double-call if already correct: frappe.cache()(). → frappe.cache().
for method in $METHODS; do
    find "$FAC_PATH/frappe_assistant_core/" -name "*.py" -not -path "*__pycache__*" \
        -exec sed -i "s/frappe\.cache()()\.${method}/frappe.cache().${method}/g" {} \;
done

echo "  Done!"

# Step 2: Fix @redis_cache(...) → @redis_cache() and @site_cache(...) → @site_cache()
# Frappe v14 redis_cache/site_cache don't accept ANY kwargs
echo ""
echo "Step 2: Fixing @redis_cache and @site_cache decorators..."
find "$FAC_PATH/frappe_assistant_core/" -name "*.py" -not -path "*__pycache__*" \
    -exec sed -i 's/@redis_cache([^)]*)/@redis_cache()/g' {} \;
find "$FAC_PATH/frappe_assistant_core/" -name "*.py" -not -path "*__pycache__*" \
    -exec sed -i 's/@site_cache([^)]*)/@site_cache()/g' {} \;
echo "  Done!"

# Step 3: Verify
echo ""
echo "Step 3: Verifying..."
REMAINING=$(grep -rn "frappe\.cache\." "$FAC_PATH/frappe_assistant_core/" --include="*.py" | grep -v __pycache__ | grep -v "frappe\.cache()" | wc -l)
if [ "$REMAINING" -eq 0 ]; then
    echo "  ✅ All fixes applied — no bare frappe.cache. remaining"
else
    echo "  ⚠️  $REMAINING lines still have bare frappe.cache. — check manually"
    grep -rn "frappe\.cache\." "$FAC_PATH/frappe_assistant_core/" --include="*.py" | grep -v __pycache__ | grep -v "frappe\.cache()" | head -5
fi

echo ""
echo "═══ Fix complete! Restart bench: sudo supervisorctl restart all ═══"

# Step 2b: Fix redis_cache/site_cache import (may not exist in Frappe v14)
echo ""
echo "Step 2b: Adding fallback for redis_cache/site_cache import..."
python3 -c "
path = '$FAC_PATH/frappe_assistant_core/utils/cache.py'
with open(path, 'r') as f:
    content = f.read()
old_import = 'from frappe.utils.caching import redis_cache, site_cache'
fallback = '''# Frappe v14 compat: redis_cache/site_cache may not exist
try:
    from frappe.utils.caching import redis_cache, site_cache
except (ImportError, AttributeError):
    def redis_cache(*args, **kwargs):
        def decorator(func):
            return func
        if args and callable(args[0]):
            return args[0]
        return decorator
    def site_cache(*args, **kwargs):
        def decorator(func):
            return func
        if args and callable(args[0]):
            return args[0]
        return decorator'''
if old_import in content and 'try:' not in content.split(old_import)[0][-20:]:
    content = content.replace(old_import, fallback)
    with open(path, 'w') as f:
        f.write(content)
    print('  Added fallback import')
else:
    print('  Already has fallback or different import')
"
