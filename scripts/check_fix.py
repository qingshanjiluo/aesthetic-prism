# -*- coding: utf-8 -*-
"""Verify loaded prune_state_dict source contains fixes + .pyc staleness check."""
import inspect

import aesthetic_prism.distill as D

print("module file:", D.__file__)
src = inspect.getsource(D.prune_state_dict)
print("has dw3.bias fix:", "dw3.bias" in src)
print("has dw5.bias fix:", "dw5.bias" in src)
print("mlp.2 slices:", src.count('mlp.2.weight'))
