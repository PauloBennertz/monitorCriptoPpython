Monitor de Criptomoedas com Análise Técnica
📖 Sobre o Projeto
Este é um avançado monitor de criptomoedas para desktop (Windows), desenvolvido em Python com uma interface gráfica moderna. O programa permite o acompanhamento em tempo real de múltiplas criptomoedas da Binance, oferecendo não apenas o preço atual, mas também insights de análise técnica para auxiliar na tomada de decisões.

O projeto foi construído com foco em usabilidade, permitindo que o usuário configure alertas personalizados tanto de preço quanto de indicadores técnicos, e receba notificações visuais e sonoras.

✨ Funcionalidades Principais
Monitoramento em Tempo Real: Acompanhe o preço e a variação de 24 horas de múltiplas criptomoedas simultaneamente.

Análise Técnica Automática: O programa calcula e exibe automaticamente:

RSI (Índice de Força Relativa): Identifica se um ativo está sobrecomprado ou sobrevendido.

Bandas de Bollinger: Mostra se o preço está "esticado" em relação à sua volatilidade normal.

Sistema de Alertas Inteligente: Crie dois tipos de alertas:

Alerta de Preço: Seja notificado quando uma moeda atinge um valor de alta ou baixa que você definiu.

Alerta de Análise Técnica: Receba um aviso quando uma moeda entrar em estado de "SOBRECOMPRADO", "SOBREVENDIDO", ou cruzar as Bandas de Bollinger.

Notificações Completas: Os alertas são entregues através de:

Um pop-up na tela.

Um alerta sonoro personalizável para cada tipo de evento.

(Opcional) Uma mensagem direta no seu Telegram.

Gerenciamento Centralizado: Uma interface intuitiva para adicionar, editar e remover todos os seus alertas, com busca inteligente de moedas e pré-visualização de sons.

Minimizar para a Bandeja: O programa pode ser minimizado para a bandeja do sistema (ao lado do relógio), continuando a monitorar seus ativos em segundo plano sem poluir sua área de trabalho.

Histórico e Legenda: Todas as notificações são salvas em um histórico, e uma aba de legenda explica o significado de cada sinal técnico.

🚀 Como Usar
Configuração Inicial:

Abra o arquivo config.json.

(Opcional) Se desejar receber alertas no Telegram, insira seu telegram_bot_token e telegram_chat_id.

Execução:

Execute o arquivo MonitorCripto.exe que está na pasta dist/MonitorCripto.

Gerenciando Alertas:

Na tela principal, clique em "Gerenciar Alertas".

Use os botões para Adicionar, Editar ou Remover os alertas.

Ao adicionar, você pode escolher entre um alerta de preço ou de análise técnica e personalizar o som.

Monitoramento:

A tela principal exibirá os dados em tempo real. A coluna "Status da Análise" mostrará os sinais de compra ou venda com cores para fácil identificação.

🛠️ Ferramentas e Créditos
Linguagem: Python

Interface Gráfica: Tkinter com a biblioteca ttkbootstrap para o tema moderno.

Análise de Dados: Biblioteca pandas para cálculos de indicadores.

API: Os dados de mercado são obtidos em tempo real da API pública da Binance.

Sons dos Alertas: Os arquivos de áudio padrão foram gerados utilizando a ferramenta de texto para fala do Google AI Studio (aistudio.google.com).

Este projeto é um exemplo prático de como utilizar Python para criar ferramentas poderosas de análise de dados e automação para o mercado financeiro.