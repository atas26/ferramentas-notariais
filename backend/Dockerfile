# Dockerfile do backend da Consulta PEP (Node/Express).
# Build a partir da pasta backend/:  docker build -t portal-pep ./backend
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY . .

# IMPORTANTE (LGPD): a base data/pep.csv (dado pessoal, 23 MB) NÃO é embutida na
# imagem — ela é ignorada no build (ver backend/.dockerignore) e deve ser fornecida
# em tempo de execução via volume, p.ex. no docker-compose:
#   volumes:
#     - /srv/portal/pep-data/pep.csv:/app/data/pep.csv:ro

ENV NODE_ENV=production
ENV PORT=8000
EXPOSE 8000

CMD ["node", "server.js"]
