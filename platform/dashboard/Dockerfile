FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN NODE_ENV=development npm install

COPY . .

EXPOSE 6001

CMD ["npm", "run", "dev"]
