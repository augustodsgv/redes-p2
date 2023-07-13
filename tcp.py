import asyncio, struct
from grader.tcputils import *
import random


class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede            # rede é um objeto do tipo IP 
        self.porta = porta          # Porta que o processo do servidor está
        self.conexoes = {}          # dicionário com todas as conexões que o servidor tem atualmente
        self.callback = None        # ???
        self.rede.registrar_recebedor(self._rdt_rcv)    # Aqui está registrando que a função _rdt_rcv será chamada quando um pacote
                                                        # chegar no ip indicado

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """
        self.callback = callback

    def _rdt_rcv(self, src_addr, dst_addr, segment):        # Função que trata o recebimento de mensagens
        src_port, dst_port, seq_no, ack_no, \
            flags, window_size, checksum, urg_ptr = read_header(segment)           # Pegando os atributos do cabeçalho do segmento separadamente
        if dst_port != self.porta:                                                 # se a porta destino não for a porta do servidor, ignora 
            # Ignora segmentos que não são destinados à porta do nosso servidor
            return
        if not self.rede.ignore_checksum and calc_checksum(segment, src_addr, dst_addr) != 0:   # Calculando se o checksum está correto
            print('descartando segmento com checksum incorreto')
            return
        payload = segment[4*(flags>>12):]               # Separando o payload do segmento
        id_conexao = (src_addr, src_port, dst_addr, dst_port)       # Criando uma variável que contém o identificado da conexão
        if (flags & FLAGS_SYN) == FLAGS_SYN:                        # Verificando se é uma nova conexão
            print('criando nova conexão')
            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, seq_no + 1)         ### Adicionei o valor de seq_no dentro da conexão, pois é aleatório
        
            ### Criando o header com dst_port e src_port invertidos (a origem agora é o destino do remetente, e vice versa)
            ### o ACK é o seq_no + 1, pois indicar o valor do próximo pacote que o remetente deve enviar
            ### Envia as flags ACK e SYN, para aceitar o handshake
            ### Usa-se o operador | para agrupar flags, mas poderia-se usar o operador + entre elas
            if self.callback:                   # Coloca a conexão como aceita que a conexão foi aceita
                self.callback(conexao)
            conexao.hand_shake()
            
        elif id_conexao in self.conexoes:                   # Caso não seja uma conexão nova, verifica se já é uma conexão estabelecida
            # Passa para a conexão adequada se ela já estiver estabelecida
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)

        else:                                                           # Se não for uma conexão nova e não tiver SYN levanta um "erro"
            print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
                  (src_addr, src_port, dst_addr, dst_port))


class Conexao:
    def __init__(self, servidor, id_conexao, ack_no):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.callback = None
        self.timer = asyncio.get_event_loop().call_later(1, self._exemplo_timer)  # um timer pode ser criado assim; esta linha é só um exemplo e pode ser removida
        #self.timer.cancel()   # é possível cancelar o timer chamando esse método; esta linha é só um exemplo e pode ser removida
        self.seq_no = random.randint(0, 0xffff)            ### Adicionando o valor de seq_no, para indicar o valor atual do número de sequencia
        self.ack_no = ack_no

    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        print('Este é um exemplo de como fazer um timer')

    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        ## Verificando se o pacote está na sequencia correta
        ## O len do payload tem que ser maior que 0 para não responder ACKs
        if seq_no == self.ack_no and len(payload) > 0:       # Caso esteja recebendo o pacote certo, ou seja, o seq_no é o mesmo do último ack_no
            self.ack_no += len(payload) ## Aumentando o valor do ACK para indicar o próximo valor que quer receber
            
            self.callback(self, payload)  ## Enviando os dados para a camada de aplicação

            self.send_ack()
        # TODO: trate aqui o recebimento de segmentos provenientes da camada de rede.
        # Chame self.callback(self, dados) para passar dados para a camada de aplicação após
        # garantir que eles não sejam duplicados e que tenham sido recebidos em ordem.
    # Os métodos abaixo fazem parte da API

    def hand_shake(self):
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        header = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_SYN | FLAGS_ACK) 
        self.servidor.rede.enviar(fix_checksum(header, dst_addr, src_addr), src_addr)        ## Não sei pq usei isso
        self.seq_no += 1

    # Função que envia a confirmação dos dados
    def send_ack(self):
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        header = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK) 
        self.servidor.rede.enviar(fix_checksum(header, dst_addr, src_addr), src_addr)        ## Não sei pq usei isso

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados = ''):
        """
        Usado pela camada de aplicação para enviar dados
        """
        # TODO: implemente aqui o envio de dados.
        # Chame self.servidor.rede.enviar(segmento, dest_addr) para enviar o segmento
        
        src_addr, src_port, dst_addr, dst_port = self.id_conexao    # Pegando dados da conexão
        
        while len(dados) > 0:
            segmento = dados[:MSS]      # -1 para contar o tamanho do header
            dados = dados[MSS:]

            header = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK)
            self.servidor.rede.enviar(fix_checksum(header + segmento, dst_addr, src_addr), self.id_conexao[0])            ## Colocando aqui o endereço do cliente da conexão
            self.seq_no += len (segmento)

        

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        pass
