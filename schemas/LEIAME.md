# XSDs oficiais

Baixe o pacote de schemas na documentação técnica do Portal Nacional da NFS-e
(https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual)
e extraia aqui TODOS os .xsd na mesma pasta (o DPS importa os demais:
tipos simples, tipos complexos, xmldsig-core-schema).

O arquivo de entrada para validar a DPS é o `DPS_v*.xsd`.

O repositório versiona só a v1.01, em `schemas/1.01/`. A v1.00 não era usada e foi removida
(o conteúdo continua no histórico do git, até o commit `427d47c`).

Origem e licença: os arquivos são do Portal Nacional da NFS-e (página acima), que lista hoje o
pacote `NFSe-ESQUEMAS_XSD-v1.01-20260209` e publica o conteúdo do site sob a licença Creative
Commons Atribuição-SemDerivações 3.0 Não Adaptada (https://creativecommons.org/licenses/by-nd/3.0/deed.pt_BR).
Aqui eles são redistribuídos sem alteração.

Os arquivos oficiais não são editados. A validação offline usa uma cópia gerada em
`schemas/<versão>-local/` (fora do git) por `scripts/preparar_xsd.py`, sem os `^` e `$`
dos padrões; `scripts/gerar_dps.py` a regenera a cada execução.
