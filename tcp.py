import asyncio, threading, time
from tcputils import *
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
            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, seq_no + 1)         ### Adicionei o valor de seq_no dentro da conexão, pois é aleatório
        
            ### Criando o header com dst_port e src_port invertidos (a origem agora é o destino do remetente, e vice versa)
            ### o ACK é o seq_no + 1, pois indicar o valor do próximo pacote que o remetente deve enviar
            ### Envia as flags ACK e SYN, para aceitar o handshake
            ### Usa-se o operador | para agrupar flags, mas poderia-se usar o operador + entre elas
            if self.callback:                   # Coloca a conexão como aceita que a conexão foi aceita
                self.callback(conexao)
            conexao.hand_shake()
        elif id_conexao in self.conexoes:                   # Caso não seja uma conexão nova, verifica se já é uma conexão estabelecida
            if (flags & (FLAGS_ACK | FLAGS_FIN)) == FLAGS_ACK | FLAGS_FIN:      # Se deseja finalizar
                self.conexoes[id_conexao].recebe_fechar()
            # Passa para a conexão adequada se ela já estiver estabelecida
            else:
                self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)

        else:                                                           # Se não for uma conexão nova e não tiver SYN levanta um "erro"
            print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
                  (src_addr, src_port, dst_addr, dst_port))
            


class Conexao:
    def __init__(self, servidor, id_conexao, ack_no):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.callback = None
        self.timer = None  # um timer pode ser criado assim; esta linha é só um exemplo e pode ser removida
        self.seq_no = random.randint(0, 0xffff)            ### Adicionando o valor de seq_no, para indicar o valor atual do número de sequencia
        self.ack_no = ack_no
        self.esperando_ack_fin = False
        self.buffer_envio = b''

        # Atributos relacionados ao timer de envio
        self.time_interval = 0.5        # Inicializando o tempo como 0.5 arbitrariamente
        self.estimatedRTT = None
        self.devRTT = None
        self.t0 = None
        self.n_tentativa = 0         # Guarda qual tentativa de envio é essa

    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        ## Verificando se o pacote está na sequencia correta
        ## O len do payload tem que ser maior que 0 para não responder ACKs
        if seq_no == self.ack_no:       
            if len(payload) > 0:    # Caso esteja recebendo o pacote certo, ou seja, o seq_no é o mesmo do último ack_no
                self.ack_no += len(payload) ## Aumentando o valor do ACK para indicar o próximo valor que quer receber
                
                self.callback(self, payload)  ## Enviando os dados para a camada de aplicação

                self.send_ack()
            # Verificando se estava esperando receber ACK
            if len(self.buffer_envio) > 0:
                if self.n_tentativa == 1:             # Só conta caso seja o primeiro envio
                    t1 = time.time()                # Pegando o momento de recebimento do ack
                    self._calc_time_interval(t1 - self.t0)          # Caculando o novo time interval
                    print(f'Demorou {t1 - self.t0} s para a resposta')
                    self.t0 = None

                self._stop_timer()         # Parando o timer
                self.seq_no += len(self.buffer_envio[:MSS])            # Incrementando o seq_no
                self.buffer_envio = self.buffer_envio[MSS:]      # Removendo o primeiro pacote da fila
                if len(self.buffer_envio) > 0:
                    self.fazEnvio()
                self.n_tentativa = 0                            # Caso tenha recebido o ACK significa que não se precisa mais continuar tentando enviar

    def hand_shake(self):
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        header = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_SYN | FLAGS_ACK) 
        self.servidor.rede.enviar(fix_checksum(header, dst_addr, src_addr), src_addr)        ## Não sei pq usei isso
        self.seq_no += 1

    # Função que envia a confirmação dos dados
    def send_ack(self):
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        header = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK) 
        self.servidor.rede.enviar(fix_checksum(header, dst_addr, src_addr), src_addr)       ## Não sei pq usei isso
        

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    # Função que coloca os dados em buffer e chama a função que faz o envio de fato
    def enviar(self, dados):     
        self.buffer_envio += dados           # Coloca os dados em buffer
        self.fazEnvio()                     # Envia os primeiros dados do buffer sem precisar esperar o timer

    # Função que pega os dados do buffer e envia
    def fazEnvio(self):
        src_addr, src_port, dst_addr, dst_port = self.id_conexao    # Pegando informações da conexão
        segmento = self.buffer_envio[:MSS]                          # Pegando os primeiros MSS bytes do buffer para enviar
        header = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_ACK)
        self.servidor.rede.enviar(fix_checksum(header + segmento, dst_addr, src_addr), src_addr)

        self.t0 = time.time()                                       # Iniciando o contador de tempo do cálculo do TimeInterval
        self._start_timer()


    '''Funções referentes ao timer'''
    # Inicia o timer e chama a função de envio
    def _start_timer(self):
        self._stop_timer()
        self.timer = asyncio.get_event_loop().call_later(self.time_interval, self.fazEnvio)
        self.n_tentativa += 1

    # Para o timer
    def _stop_timer(self):
        if self.timer != None:
            self.timer.cancel()

    # Calcula o intervalo de tempo
    def _calc_time_interval(self, sampleRTT):
        self.is_reenvio = -1
        if self.estimatedRTT == None:       # Caso seja o primeiro cálculo do TimeInterval
            self.estimatedRTT = sampleRTT
            self.devRTT = sampleRTT / 2
        else:
            # Calculando o Estimated RTT
            alpha = 0.125
            self.estimatedRTT = (1 - alpha) * self.estimatedRTT + alpha * sampleRTT
            
            # Calculando o Deviation RTT
            beta = 0.25
            self.devRTT = (1 - beta) * self.devRTT + beta * abs(sampleRTT - self.estimatedRTT)

        # Calulando o Time Interval
        self.time_interval = self.estimatedRTT + 4 * self.devRTT
        print(f'S: Esperando {self.time_interval}s')

    # Esta função trata o recebimento do FIN, envia o ACK e envia um sinal de fechamento
    def recebe_fechar(self):
        self.ack_no += 1               ## Convenciona-se que, quando se recebe FIN, incrementa-se o ack
        self.callback(self, b'')       ## Enviando mensagem de fechamento para a camada de aplicação
        self.send_ack()
        del self.servidor.conexoes[self.id_conexao]

    # Esta função envia um FIN e receber o ACK
    def fechar(self):
        src_addr, src_port, dst_addr, dst_port = self.id_conexao    # Pegando dados da conexão
        if self.esperando_ack_fin:      # Caso esteja esperando o ACK do FIN
            # Deletando no servidor
            #self.send_ack()
            del self.servidor.conexoes[self.id_conexao]

        else:                           # Caso esteja enviando o FIN
            # Enviando ACK de confirmação
            header = make_header(dst_port, src_port, self.seq_no, self.ack_no, FLAGS_FIN)
            self.callback(self, b'')
            self.servidor.rede.enviar(fix_checksum(header, dst_addr, src_addr), src_addr)
            # Setando estado de espera do ACK
            self.esperando_ack_fin = True
            self.seq_no += 1