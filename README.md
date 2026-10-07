## Brainstorming: estrutura da Prova de Conceito (NFS-e Nacional)

### Vai ser uma API, Cliente HTTP, script?

> Não é "API vs cliente HTTP vs script": são camadas, e a PoC deve começar pela mais interna.

1. Biblioteca/cliente Python (o núcleo): monta a DPS, assina o XML, comprime, faz o POST com mTLS, interpreta a resposta.
2. Script/CLI (a PoC em si): chama o cliente com uma DPS de exemplo no ambiente de homologação.
3. API (FastAPI): só entra depois, como casca fina em volta do cliente, quando houver um consumidor real (seu front-end, ERP de clientes, etc.).

> Recomendação: PoC = cliente + script. Se a PoC funcionar, a API é só expor o que já existe. Fazer a API primeiro significa debugar assinatura, mTLS e HTTP ao mesmo tempo que lida com rotas, auth e deploy.

### O que a PoC precisa provar?

O risco real do projeto está nesta ordem de dificuldade:

1. mTLS com certificado A1 funcionando em Python
2. Geração e assinatura do XML da DPS (XMLDSIG): normalmente a parte mais trabalhosa
3. GZip + Base64 do XML e o envio no formato JSON esperado
4. Receber a NFS-e, decodificar e validar o retorno
5. Consultar a nota pela chave de acesso e baixar o DANFSe

Se esses cinco passos funcionarem em homologação, o resto é engenharia de produto.

### Bibliotecas candidatas:
- HTTP/mTLS: httpx ou requests (com PFX convertido em PEM, ou requests-pkcs12)
-Certificado: cryptography
-Assinatura XML: signxml ou lxml + xmlsec (valide qual gera o formato exato que o padrão nacional exige)
-Modelagem: pydantic para a DPS
-API futura: FastAPI

### Estrutura inicial

```sh
nfse-poc/
├── .env                  # caminhos, senha do cert, base URL (fora do git)
├── certs/                # .pfx de homologação (fora do git)
├── src/
│   ├── config.py         # carrega ambiente (homologação/produção)
│   ├── certificado.py    # carrega PFX/A1, expõe cert+chave
│   ├── dps.py            # modelo da DPS e geração do XML
│   ├── assinatura.py     # XMLDSIG
│   ├── codec.py          # gzip + base64 (ida e volta)
│   ├── client.py         # HTTP com mTLS (POST /nfse, GET /nfse/{chave}...)
│   └── erros.py          # exceções mapeadas dos retornos da API
├── scripts/
│   ├── emitir.py         # emite uma nota de teste
│   ├── consultar.py      # consulta por chave
│   └── baixar_danfse.py
└── tests/
```