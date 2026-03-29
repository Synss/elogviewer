# Setup Gentoo VM

## Vagrant VM

Options:
 - `gentoo_run_sync`: Call `emerge --sync` (skipped if tree is less than 24 h old).
 - `gentoo_base_qt_use_flag`: Qt version USE flag. Default: `qt6`.
 - `gentoo_manage_python_targets`: Write `PYTHON_TARGETS` and `PYTHON_SINGLE_TARGET`
   to `make.conf`. Default: `true`; auto-detects the system Python version.
 - `python_targets`, `python_single_target`: Override the detected version.
   Pass the bare version string — the `-*` exclusion prefix is added by the template.

```
ansible-playbook site.yml -e gentoo_run_sync=true
ansible-playbook site.yml -e gentoo_base_qt_use_flag=qt5
ansible-playbook site.yml -e python_targets=python3_11 -e python_single_target=python3_11
ansible-playbook site.yml -e gentoo_manage_python_targets=false
```

Log in with `just ssh`.


## Docker deployment/e2e tests

```
cd vm && uv run --extra vm molecule test --scenario-name e2e
```


## Unit tests

```
cd vm/roles/gentoo_base && uv run --extra vm molecule test
```
