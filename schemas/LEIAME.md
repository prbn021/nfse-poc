# XSDs oficiais

Baixe o pacote de schemas na documentação técnica do Portal Nacional da NFS-e
(https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual)
e extraia aqui TODOS os .xsd na mesma pasta (o DPS importa os demais:
tipos simples, tipos complexos, xmldsig-core-schema).

O arquivo de entrada para validar a DPS é o `DPS_v*.xsd`.

O repositório versiona só a v1.01, em `schemas/1.01/`. A v1.00 não era usada e foi removida
(o conteúdo continua no histórico do git, até o commit `427d47c`).

Os arquivos oficiais não são editados. A validação offline usa uma cópia gerada em
`schemas/<versão>-local/` (fora do git) por `scripts/preparar_xsd.py`, sem os `^` e `$`
dos padrões; `scripts/gerar_dps.py` a regenera a cada execução.
