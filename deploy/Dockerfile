# Dockerfile do site "ferramentas-notariais" (Node/Express - server.js).
# Serve as páginas e faz o guard de acesso. Fonte da verdade = este repositório.
FROM node:20-alpine

WORKDIR /app

# Instala só dependências de produção (usa o package.json da RAIZ do repo).
COPY package.json package-lock.json* ./
RUN npm install --omit=dev

# Copia o restante do site (rode o build de imagem a partir da raiz do repo:
#   docker build -f deploy/Dockerfile -t portal-ferramentas .
COPY . .

ENV NODE_ENV=production
ENV PORT=3000
EXPOSE 3000

CMD ["node", "server.js"]
