# XSDs oficiais

Cada pacote oficial de XSDs fica numa pasta própria, com o nome do pacote, e com todos os
`.xsd` do zip, sem nenhuma alteração (o DPS importa os demais: tipos simples, tipos complexos,
xmldsig-core-schema). O `SHA256SUMS` de cada pasta lista os arquivos e o SHA-256 de cada um;
o `tests/test_schemas.py` o confere em G-1, e o G-3 recusa arquivo de pacote alterado, apagado
ou renomeado (INV-01, DEC-066). A pasta `schemas/` não tem cópia derivada.

## Pacotes no repositório

| Pasta | Pacote | Origem | Zip (SHA-256) | Ativo |
|-------|--------|--------|---------------|-------|
| `v1.01-prodrest-20260727/` | `NFSe-ESQUEMAS_XSD-PRODREST-v1.01-20260727` (produção restrita) | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/esquemas-nfse-rtc-v1-01-20260727.zip, baixado em 2026-10-14 | `6c7e0510d3ecff4454f291f4e10b742d27a4818f23aab181494f96d0ea79f3dc` | sim |

O pacote ativo é o padrão de `NFSE_XSD_DIR` (`src/config.py`, `.env.example`). Só há um.

Licença: o Portal Nacional da NFS-e publica o conteúdo do site sob a licença Creative Commons
Atribuição-SemDerivações 3.0 Não Adaptada
(https://creativecommons.org/licenses/by-nd/3.0/deed.pt_BR). Aqui os arquivos são
redistribuídos sem alteração.

Pacotes que saíram (o conteúdo continua no histórico do git):

- `schemas/1.00/`: não era usado; removido na T-009 (commit `427d47c`).
- `schemas/1.01/`: pacote de produção `NFSe-ESQUEMAS_XSD-v1.01-20260209`; removido na T-038.
  O padrão de `serie` dele tinha `^` e `$`, que em XML Schema são literais, e a validação
  usava uma cópia sem as âncoras (DEC-003). O pacote de produção restrita já vem sem elas.

## Como entrar um pacote novo

1. Baixar o zip da página de documentação técnica do Portal Nacional da NFS-e e registrar
   em `docs/SOURCES.md` a URL, a data e o SHA-256 do zip.
2. Extrair todos os `.xsd`, sem alteração, numa pasta nova `schemas/v<versão>[-prodrest]-<data>/`
   (nome tirado do nome do pacote). Os arquivos ficam com os bytes do zip (`schemas/** -text`
   no `.gitattributes`).
3. Gerar o `SHA256SUMS` da pasta (`<sha256>  <arquivo>`, uma linha por arquivo) e acrescentar
   a linha do pacote na tabela acima.
4. Comparar arquivo por arquivo com o pacote ativo e registrar as diferenças em
   `docs/SOURCES.md`.
5. Rodar os gates com `NFSE_XSD_DIR` apontando para a pasta nova.
6. Trocar o pacote ativo (`PACOTE_XSD` em `src/config.py` e `.env.example`) só com uma DEC.
   O pacote substituído sai do repositório na mesma task, também com DEC, e os testes de
   `tests/test_schemas.py` são ajustados.

Se um pacote vier com defeito que impeça a validação, a correção é decidida nessa hora, com
DEC; os arquivos oficiais nunca são editados.
