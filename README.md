# Arquivo → PDF

Aplicação local para descarregar imagens de visualizadores de arquivo e reuni-las num PDF.

## Utilização

1. Faça duplo clique em `Iniciar.bat`.
2. Cole o endereço do documento.
3. Escolha as páginas e a qualidade.
4. Prima **Criar PDF** e, no fim, **Descarregar PDF**.

Os PDFs também ficam guardados em `output/pdf`.

## Requisitos

- Windows com Python 3.11 ou mais recente.
- ImageMagick 7 com suporte TIFF e o comando `magick` disponível no `PATH`.

A aplicação usa apenas a biblioteca padrão do Python. Não é necessário instalar pacotes Python.

## Visualizadores

- **Archeevo:** disponível. O adaptador usa os pontos de acesso públicos do próprio visualizador.
- **Digitarq:** disponível para endereços `/fileViewer/{id}`. O adaptador consulta os metadados e a lista paginada de objetos digitais, usando a disseminação original ou a miniatura pública de cada ficheiro.
- **Outros:** podem ser adicionados criando um novo adaptador em `archive_pdf/adapters` e registando-o em `registry.py`.

## Funcionamento e privacidade

O servidor só escuta em `127.0.0.1`, portanto não fica acessível a outros computadores. As imagens são transferidas diretamente do arquivo para este computador, convertidas para JPEG e integradas no PDF. Pedidos falhados são repetidos automaticamente e um trabalho interrompido pode ser retomado sem voltar a converter páginas já concluídas.

Use a ferramenta respeitando as condições de utilização, os direitos de reprodução e a capacidade dos servidores dos arquivos.

## Desenvolvimento

```powershell
python -m unittest discover -s tests -v
python app.py --no-browser
```
