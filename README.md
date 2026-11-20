# GICNEXT (gic_erp)

Plug-and-play modular ERP for Gujranwala SMEs, built on ERPNext v15 by the Gujranwala
Incubation Center.

[![CI](https://github.com/meerhamza00/gic-erp/actions/workflows/ci.yml/badge.svg)](https://github.com/meerhamza00/gic-erp/actions/workflows/ci.yml)

## What it adds to ERPNext

- **Industry Profile switchboard** and one-click industry blueprints (Foundry, Mandi,
  Importer, Sanitary) with Pakistani tax templates.
- **Munshi-friendly desk:** local units (Mann, Bori, Petti), a simple form mode.
- **Foundry:** burning loss on melts, thekedar work log.
- **Kacha / Pakka** dual billing and WhatsApp alerts.
- **FBR Digital Invoicing** (PRAL) with sandbox mode and QR codes.

## Development

```bash
# from the workspace root (ERP - GIC/)
./scripts/dev-up.sh      # http://localhost:8000
./scripts/test.sh        # gic_erp tests
```

New laptop: `dev/scripts/bootstrap.sh`. Contribution rules: [CONTRIBUTING.md](CONTRIBUTING.md).

## Releases and deployment

Docker images built and tested in GitHub Actions, attached to each GitHub Release and
deployed over SSH to an Ubuntu server running the frappe_docker stack. See
[docs/DEVOPS.md](docs/DEVOPS.md) and [ADR 0001](docs/adr/0001-devops-platform.md).

## License

MIT
