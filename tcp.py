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

            header = make_header(dst_port, src_port, conexao.seq_no, conexao.ack_no, FLAGS_SYN | FLAGS_ACK) 
            conexao.enviar(fix_checksum(header, dst_addr, src_addr))        ## Não sei pq usei isso
            
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
        print(f'cliente  : seq_no {seq_no} ack_no {ack_no}')
        print(f'servidor : seq_no {self.seq_no} ack_no {self.ack_no}')
        ## Verificando se o pacote está na sequencia correta
        if seq_no == self.ack_no:       # Caso esteja recebendo o pacote certo, ou seja, o seq_no é o mesmo do último ack_no
            # Aumentando o valor do ACK para indicar o próximo valor que quer receber
            self.ack_no += len(payload)
            print(f'ack + payload : {self.ack_no}')
            print('recebido payload: %r' % payload)
            self.callback(self, payload)  ## Enviando os dados para a camada de aplicação
            #id_conexao = (src_addr, src_port, dst_addr, dst_port)
            header = make_header(self.id_conexao[3], self.id_conexao[1], self.seq_no, self.ack_no, FLAGS_ACK)
            self.enviar(fix_checksum(header, self.id_conexao[2], self.id_conexao[0]))
        # TODO: trate aqui o recebimento de segmentos provenientes da camada de rede.
        # Chame self.callback(self, dados) para passar dados para a camada de aplicação após
        # garantir que eles não sejam duplicados e que tenham sido recebidos em ordem.
        
    # Os métodos abaixo fazem parte da API

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados):
        """
        Usado pela camada de aplicação para enviar dados
        """
        # TODO: implemente aqui o envio de dados.
        # Chame self.servidor.rede.enviar(segmento, dest_addr) para enviar o segmento

        # Criando o arquivo
        self.servidor.rede.enviar(dados, self.id_conexao[0])            ## Colocando aqui o endereço do cliente da conexão
        # que você construir para a camada de rede.
        #print(self.callback)        
        #self.callback(self, dados)
        self.seq_no+=len(dados)
        

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        pass
