# Documentação oficial do Sistema Nacional NFS-e

Anexos (planilhas) e manuais (PDF) publicados no Portal Nacional da NFS-e, na página
https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual

Os arquivos foram entregues ao projeto em 2026-10-07 e versionados em 2026-10-08, sem alteração.
A URL de download de cada um não foi registrada, e eles não foram comparados byte a byte com os
que a página publica hoje.

Exceção: `anexovi-leiautesrn_rtc_ibscbs-v1-04-01-nt009.xlsx` (Anexo VI da Nota Técnica 009 v1.01,
leiaute e regras da Reforma Tributária do Consumo) vem da página
https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc
(link `…/rtc/anexovi-leiautesrn_rtc_ibscbs-v1-04-01-nt009.xlsx`). Foi baixado pelo humano e
versionado em 2026-10-14 (T-036), sem alteração.

Também dessa página, baixados pelo agente e versionados em 2026-10-14 (T-034, DEC-069), sem
alteração: `anexovii-indop_ibscbs_v1-03-00-nt009.xlsx` (Anexo VII, tabela do código indicador
da operação, `cIndOp`) e `anexoviii-correlacaoitemnbsindopcclasstrib_ibscbs_v1-01-00.xlsx`
(Anexo VIII, correlação entre item da LC 116, NBS, `cIndOp` e `cClassTrib`), nos links
`…/rtc/<nome do arquivo>`.

Licença: a página declara que "todo o conteúdo deste site está publicado sob a licença Creative
Commons Atribuição-SemDerivações 3.0 Não Adaptada" (https://creativecommons.org/licenses/by-nd/3.0/deed.pt_BR).
Aqui os arquivos são redistribuídos sem alteração.

Esta pasta é frozen: os arquivos nunca são editados. `SHA256SUMS` traz o SHA-256 de cada um, e
`tests/test_gov_docs.py` falha se algum mudar, sumir ou aparecer sem estar no manifesto. Uma versão
nova de um documento entra como arquivo novo, com o manifesto atualizado e uma decisão registrada
em `docs/SPEC.md`.

O resto de `docs/referencia/` fica fora do git: é onde ficam notas de clientes e outros arquivos
com dados reais.
