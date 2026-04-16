# Napro Suite

Napro Suite é uma aplicação composta por um servidor (Backend) e um cliente de telemetria (Frontend) criados para comunicar e plotar dados do Módulo de Comunicação NAPRO de modo contínuo.

## Estrutura do Projeto

- `backend/`: Contém o servidor de ponte serial e TCP.
  - `server_app.py`: Servidor central que interage via porta serial com o hardware e disponibiliza dados aos clientes em JSON via TCP (porta 9999).
- `frontend/`: Contém a interface do cliente e visualizador de telemetria.
  - `client_app.py`: Cliente desktop desenvolvido com Tkinter e Matplotlib que exibe os gráficos contínuos e log quantitativo de poluentes e parâmetros gerados pelo equipamento.

## Como Executar pelo Código Fonte

### Pré-requisitos
Certifique-se de ter o Python 3 instalado.

**No Backend:**
\`\`\`bash
cd backend
pip install -r requirements.txt
python server_app.py
\`\`\`

**No Frontend:**
\`\`\`bash
cd frontend
pip install -r requirements.txt
python client_app.py
\`\`\`

## Executáveis
Os executáveis pré-compilados do servidor e cliente (`.exe`) podem ser encontrados nas pastas `backend/dist` e `frontend/dist`. 

> **Nota**: Os executáveis são gerenciados com Git LFS neste repositório. Certifique-se de que o Git LFS esteja instalado no seu sistema.

## Funções principais
- **Servidor**: Configuração da porta de equipamento, log serial bruto para CSV, e comunicação multidirecional entre o NAPRO e softwares auxiliares (VCOM).
- **Cliente**: Monitoramento em tempo real dos índices de gases, acompanhamento do painel digital com gráficos dinâmicos estilo polígrafo, com possibilidade de salvar logs em CSV dos tempos capturados.
