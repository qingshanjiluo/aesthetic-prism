import os, sys, types
os.environ['AP_AUTH_DB'] = 'data/test_auth_fast.db'
sys.path.insert(0, 'src')
import pathlib
for p in ('data/test_auth_fast.db','data/test_auth_fast.db-wal','data/test_auth_fast.db-shm'):
    try: pathlib.Path(p).unlink()
    except OSError: pass
import aesthetic_prism.serve.auth as auth
# 强制走内置哈希（绕过慢的 passlib）
auth._HAS_PASSLIB = False
auth.init_db()
r = auth.register('bob','pw')
assert r, 'register fail'
print('REGISTER_OK bal=', r['balance'])
lg = auth.login('bob','pw')
assert lg, 'login fail'
print('LOGIN_OK bal=', lg['balance'])
assert auth.login('bob','x') is None
print('BADPW_OK')
assert auth.charge(r['id'],10,'消费','评分')
print('CHARGE_OK bal=', auth.get_wallet(r['id'])['balance'])
b=auth.buy_model(r['id'],'models/hapnet_teacher.onnx')
assert b and not b['already']
print('BUY_OK owned=', auth.owned_models(r['id']))
assert auth.verify_token(lg['token'])['id']==r['id']
print('TOKEN_OK')
print('ALL_FAST_PASS')
