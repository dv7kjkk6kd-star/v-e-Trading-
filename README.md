# Strategy Lab – samostatný web

Strategy Lab běží ve **vlastním repozitáři**. Tvůj web Kompas klidu (repozitář `1`) zůstává beze změny: nepřidává se do něj žádný soubor, odkaz ani workflow.

- Adresa po zapnutí: **https://dv7kjkk6kd-star.github.io/strategy-lab/**
- Vzhled: stejný styl jako Kompas klidu (kopie `style.css`), stejné boční menu s odkazy na tvé stránky.
- Světlý a tmavý režim se sdílí s Kompasem, protože obě stránky běží na stejné doméně.
- Z tvého webu se jen **čte** veřejný soubor `events.json` (kalendář CPI, NFP, FOMC). Když není dostupný, kalendář se doplní podle pravidel.

## Postup (asi 5 minut)

1. Na GitHubu vytvoř nový **veřejný** repozitář s názvem `strategy-lab`.
2. Nahraj do něj obsah tohoto balíčku: složky `docs`, `lab`, soubor `README.md` (Add file → Upload files).
3. Workflow přidej ručně, protože skrytá složka `.github` se přes prohlížeč často nenahraje:
   Add file → Create new file → název `.github/workflows/lab-data.yml` → vlož obsah souboru `.github/workflows/lab-data.yml` z balíčku → Commit.
4. Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save.
5. Settings → Pages → Source: *Deploy from a branch* → Branch `main`, složka `/docs` → Save.
6. Actions → **Strategy Lab – data** → Run workflow. První běh stáhne historii (pár minut).
7. Otevři https://dv7kjkk6kd-star.github.io/strategy-lab/

## Co se kdy aktualizuje

| Data | Zdroj | Jak často |
|---|---|---|
| NQ futures po minutě | Yahoo Finance (NQ=F) | každých 15 min, ne–pá |
| Denní ETF, akcie, měny, výsledky firem | Yahoo Finance | jednou denně po 16:20 NY |
| CPI, sazba Fedu, výnos 30letých, NFP | FRED | jednou denně |
| Kalendář CPI, NFP, FOMC | `events.json` z tvého webu (jen čtení) + pravidla | jednou denně |

Mozek strategií (naučené parametry) se ukládá v prohlížeči. Přenos na jiné zařízení: Nastavení a mozek → Export / Import.
