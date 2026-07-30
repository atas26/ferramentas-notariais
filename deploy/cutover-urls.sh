#!/usr/bin/env bash
# Troca as URLs dos backends de *.onrender.com para os domínios do Contabo.
#
# ⚠️ EXECUTAR SOMENTE NO CUTOVER (Fase 6), quando os backends JÁ estiverem no ar no
# Contabo. Enquanto o site rodar no Render, as URLs devem continuar em *.onrender.com,
# senão as ferramentas quebram em produção. Este script NÃO é executado
# automaticamente por nada — é você quem roda, de propósito, na virada.
#
# Uso:  bash deploy/cutover-urls.sh   (a partir da raiz do repositório)
set -euo pipefail

# 1) Ajuste os domínios novos do Contabo:
PEP="https://pep.portalnotarial.com.br"       # consulta-pep-backend
SELO="https://selo.portalnotarial.com.br"     # consulta-selo-digital-tjsp
PAGINA="https://api.portalnotarial.com.br"    # pagina-inicial (reportar link quebrado)

# 2) Substituições (idempotentes):
sed -i "s#https://consulta-pep-backend.onrender.com#${PEP}#g"      consulta-pep.html
sed -i "s#https://consulta-selo-digital-tjsp.onrender.com#${SELO}#g" consulta-selo-digital.html
sed -i "s#https://pagina-inicial.onrender.com#${PAGINA}#g"          links-uteis.html

echo "URLs trocadas. Conferência (deve ficar vazio):"
grep -rn "onrender.com" consulta-pep.html consulta-selo-digital.html links-uteis.html || echo "  (ok, nenhuma URL onrender restante nesses arquivos)"
