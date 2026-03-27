# Setup Gentoo VM

## Vagrant VM

Options
 - `gentoo_run_sync`: Call `emerge --sync`.

Example
```
ansible-playbook site.yml -e gentoo_run_sync=true
```

Log in with `just ssh`.


## Docker deployment/e2e tests

Test `uv run --extra vm molecule test --scenario-name e2e`.
