# nfse-poc

Prova de conceito de um emissor de NFS-e pela API NFS-e Nacional, em Python, no Windows.

O que existe hoje:

- gera o XML de uma DPS de exemplo (dados fictícios) a partir de dataclasses;
- valida esse XML offline contra uma cópia local do `DPS_v1.01.xsd`, que difere do oficial em uma linha (as âncoras `^` e `$` do padrão de `serie`).

O que ainda não existe: assinatura, compactação, transmissão e consulta. Nada aqui emite nota, e passar no XSD não quer dizer que o servidor aceita a DPS. O estado do projeto, as decisões e as tarefas estão em [`docs/SPEC.md`](docs/SPEC.md).

## Estrutura do projeto

```sh
nfse-poc/
├── certs/                # .pfx de homologação (fora do git)
├── docs/                 #
├── schema                #
├── scripts/
│   ├── emitir.py         # emite uma nota de teste
│   ├── consultar.py      # consulta por chave
│   └── baixar_danfse.py
├── src/
│   ├── config.py         # carrega ambiente (homologação/produção)
│   ├── certificado.py    # carrega PFX/A1, expõe cert+chave
│   ├── dps.py            # modelo da DPS e geração do XML
│   ├── assinatura.py     # XMLDSIG
│   ├── codec.py          # gzip + base64 (ida e volta)
│   ├── client.py         # HTTP com mTLS (POST /nfse, GET /nfse/{chave}...)
│   └── erros.py          # exceções mapeadas dos retornos da API
├── tests/
├── .env.example          # caminhos, senha do cert, base URL (fora do git)
└── 
```

## Requisitos

- Windows com PowerShell
- Python 3.11 (a versão fixada está em `.python-version`), com o lançador `py`
- git

## Preparar o ambiente

Na raiz do repositório:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
```

- Os dois arquivos de dependências são necessários. `requirements.txt` tem só o que a execução usa (lxml, python-dotenv); o pytest está em `requirements-dev.txt`.
- Não é preciso ativar a venv: todos os comandos chamam `.\.venv\Scripts\python.exe` diretamente.
- Para gerar a DPS e rodar os testes, o `.env` copiado serve como está. Certificado e senha ainda não são usados.
- O ambiente é sempre `homologacao` (produção restrita). `NFSE_AMBIENTE=producao` é recusado pelo código.

## Rodar

```powershell
.\.venv\Scripts\python.exe scripts\gerar_dps.py
```

O script grava a DPS em `out\DPS<42 dígitos>.xml`, imprime o XML e valida. A última linha esperada é:

```
[OK] Válida contra DPS_v1.01.xsd (cópia local em ...\schemas\1.01-local)
```

Código de saída: `0` válida, `1` inválida (os erros são listados), `2` XSD não encontrado em `NFSE_XSD_DIR`.

A cópia local dos XSDs (`schemas\1.01-local`, fora do git) é refeita a cada execução. Para gerá-la sem gerar a DPS: `.\.venv\Scripts\python.exe scripts\preparar_xsd.py`.

## Testar

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
```

Todos os testes devem passar, nenhum pulado.

As outras verificações que toda mudança precisa passar (lista completa em `docs/SPEC.md`, §8):

```powershell
.\.venv\Scripts\python.exe scripts\gerar_dps.py          # sai com código 0
git diff --exit-code main -- schemas/1.01                # sem saída: XSDs oficiais intocados
.\.venv\Scripts\python.exe scripts\checar_segredos.py    # nenhum .env ou certificado no git
```

No PowerShell, `$LASTEXITCODE` mostra o código de saída do último comando.

## Problemas comuns

| Sintoma                       | Causa e correção                                                                                                    |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `No module named pytest`      | Só o `requirements.txt` foi instalado. Rode o comando de instalação de "Preparar o ambiente", com os dois arquivos. |
| Falha em `tests/test_lock.py` | O que está instalado na venv não bate com os locks. Rode de novo o comando de instalação.                           |
| `ValueError` citando INV-02   | O `.env` tem `NFSE_AMBIENTE=producao`. Volte para `homologacao`.                                                    |
| `[!] XSD não encontrado`      | `NFSE_XSD_DIR` no `.env` não aponta para `schemas/1.01`.                                                            |
| A venv ficou inconsistente    | Apague e recrie: `Remove-Item -Recurse -Force .venv`, depois os comandos de "Preparar o ambiente".                  |

## Mudar uma dependência

Edite o `.in`, gere os dois locks de novo, nesta ordem, e reinstale. Os locks (`requirements.txt`, `requirements-dev.txt`) não são editados à mão.

```powershell
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements.txt requirements.in
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.txt requirements-dev.in
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
```

Os locks foram gerados no Windows com Python 3.11 e valem para essa plataforma.

---




