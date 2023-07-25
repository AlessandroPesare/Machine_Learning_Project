"""
stock backtester to test the model given a dataset. 
authors - Alessandro Pesare, Fabio Letizia
"""

import numpy as np
import sys
sys.path.append("/Users/alessandropesare/Desktop/ML_Project/stock_utils")
from stock_utils.simulator import simulator
from stock_utils.stock_utils import get_stock_price
from models import logistic_regression_inference
from datetime import datetime
from datetime import timedelta
import pandas as pd
from models.logistic_regression_inference import LR_v1_predict, LR_v1_sell
import warnings
from collections import OrderedDict
warnings.filterwarnings("ignore")
import os
import pickle
from tqdm import tqdm
"""
Tipo di trader che seleziona i titoli in base al valore della previsione
In sintesi, la classe backtester esegue un backtest di un modello di previsione delle azioni su un set
di dati storici specificato. Utilizza una logica di selezione dei titoli basata sulla previsione generata
dal modello e implementa una strategia di acquisto/vendita per simulare le transazioni nel tempo.
"""
class backtester(simulator):

    def __init__(self, stocks_list, model, capital, start_date, end_date, threshold = 0.99, sell_perc = 0.04, hold_till = 5,\
         stop_perc = 0.005):
        
        super().__init__(capital) #initialize simulator

        self.stocks = stocks_list  # lista di titoli azionari che verranno utilizzati nel backtest.
        self.model = model # modello di previsione delle azioni utilizzato per generare le previsioni dei prezzi delle azioni.
        self.start_date = start_date # la data di inizio del backtest.
        self.day = start_date
        self.end_date = end_date # la data di fine del backtest.
        self.status = 'buy' #the status says if the backtester is in buy mode or sell mode
        self.threshold = threshold # soglia che determina se un titolo deve essere acquistato o meno in base alla previsione generata dal modello
        self.sell_perc = sell_perc # la percentuale di guadagno al di sopra del quale viene venduta una posizione.
        self.hold_till = hold_till # il numero di giorni in cui una posizione viene mantenuta prima di essere venduta
        self.stop_perc = stop_perc # la percentuale di perdita al di sotto della quale una posizione viene venduta.

        #current directory. Crea una cartella per i risultati del backtest.
        current_dir = os.getcwd() # os.getcwd() restituisce una stringa rappresentante il percorso della directory corrente.
        results_dir = os.path.join(current_dir, 'results') # la funzione os.path.join() per combinare la directory corrente (current_dir) con il nome della cartella dei risultati ('results')
        #crea il nome della nuova cartella dei risultati. Il nome è costituito dalla rappresentazione in stringa del nome del modello (self.model.__name__),
        #seguito dai valori della soglia (self.threshold) e del parametro hold_till.
        folder_name = f'{str(self.model.__name__)}_{self.threshold}_{self.hold_till}'
        self.folder_dir = os.path.join(results_dir, folder_name)
        if not os.path.exists(self.folder_dir):
            #create a new folder
            os.makedirs(self.folder_dir)
      
    def backtest(self):
        """
        start backtesting
        """
        delta = timedelta(days = 1)
        
        #progress bar to track progress
        total_days = (self.end_date - self.start_date).days
        #variabile per tenere traccia dei giorni passati.
        d = 0
        #viene creato un oggetto tqdm per visualizzare una barra di avanzamento del backtest.
        pbar = tqdm(desc = 'Progress', total = total_days)

        while self.day <= self.end_date:
            
            #dizionario per memorizzare i risultati della scansione giornaliera delle azioni.
            self.daily_scanner = {}  
            if self.status == 'buy':
                #vengono scansionate le azioni del giorno e viene popolato il dizionario con i risultati
                self.scanner()
                if list(self.daily_scanner.keys()) != []:
                    recommended_stock = list(self.daily_scanner.keys())[0] #primo titolo azionario raccomandato
                    recommended_price = list(self.daily_scanner.values())[0][2] #prezzo raccomandato per l'azione selezionata 
                    self.buy(recommended_stock, recommended_price, self.day) #buy stock
                    # print(f'Bought {recommended_stock} for {recommended_price} on the {self.day}')
                    self.status = 'sell' #change the status to sell
                else:
                    # print('No recommendations')
                    pass
            else: #if the status is sell
                #get stock price on the day
                stocks = [key for key in self.buy_orders.keys()] # ottiene una lista di tutti i titoli azionari che rappresentano le azioni acquistate in precedenza(le azioni acquistate in precedenza vengono memorizzate nel dizionario della classe simulator).
                for s in stocks:
                    recommended_action, current_price = LR_v1_sell(s, self.buy_orders[s][3], self.buy_orders[s][0], self.day, \
                        self.sell_perc, self.hold_till, self.stop_perc)
                    # la logica di vendita nella classe backtester si basa sulla funzione LR_v1_sell
                    if recommended_action == "SELL":
                        # print(f'Sold {s} for {current_price} on {self.day}')
                        self.sell(s, current_price, self.buy_orders[s][1], self.day)
                        self.status = 'buy'              
            #go to next day
            self.day += delta
            d += 1
            pbar.update(1)
        pbar.close()
        #sell the final stock and print final capital also print stock history with the methods of the superclass (simulator)
        self.print_bag()
        self.print_summary() 
        self.save_results()      
        return
    """
    this function queries to database and get data of a particular stock on a given day back to certain amount of days
    (default is 30). 
    """
    def get_stock_data(self, stock, back_to = 30):
   
        #get start and end dates
        end = self.day
        start = self.day - timedelta(days = back_to)        
        # prediction, prediction_thresholded, close_price = LR_v1_predict(stock, start, end, threshold = 0.5)
        # attraverso il modello specificato (self.model) ottengo le previsioni, le previsioni soglia e il prezzo di chiusura per il titolo azionario specificato 
        prediction, prediction_thresholded, close_price = self.model(stock, start, end, self.threshold)
        return prediction[0], prediction_thresholded, close_price
    """
    Nella funzione scanner, viene eseguita una scansione su tutti i titoli nella lista self.stocks. 
    Viene effettuato un controllo per verificare se la previsione (prediction_thresholded) è
    inferiore a 1. Se la condizione è verificata, i dati vengono salvati nel dizionario daily_scanner.
    Inoltre, alla fine della funzione, il dizionario viene ordinato in base al valore della previsione.
    """
    def scanner(self):
        """
        scan the stocks to find good stocks
        """
        for stock in self.stocks:
            try:#to ignore the stock if no data is available. #for staturdays or sundays etc
                prediction, prediction_thresholded, close_price = self.get_stock_data(stock)
                #if prediction greater than
                if prediction_thresholded < 1: #if prediction is zero (to buy)
                    self.daily_scanner[stock] = (prediction, prediction_thresholded, close_price)
            except:
                pass

        def take_first(elem):
            return elem[1] # secondo elemento della coppia

        #ordinamento rispetto al valore associato alla chiave
        self.daily_scanner = OrderedDict(sorted(self.daily_scanner.items(), key = take_first, reverse = True))

    def save_results(self):
        """
        save history dataframe create figures and save
        """
        #save csv file
        results_df_path = os.path.join(self.folder_dir, 'history_df.csv')
        self.history_df.to_csv(results_df_path, index = False)
        
        #save params and results summary probabilmente non necessarie
        results_summary_path = os.path.join(self.folder_dir, 'results_summary')
        results_summary = [self.initial_capital, self.total_gain]
        params_path = os.path.join(self.folder_dir, 'params')
        params = [self.threshold, self.hold_till, self.sell_perc, self.stop_perc, self.start_date, self.end_date]
        
        with open(results_summary_path, 'wb') as fp:
            pickle.dump(results_summary, fp)
        with open(params_path, 'wb') as fp:
            pickle.dump(params, fp)

if __name__ == "__main__":
    #stocks list
    #dow = ['AXP', 'AMGN', 'AAPL', 'BA', 'CAT', 'CSCO', 'CVX', 'GS', 'HD', 'HON', 'IBM', 'INTC',\
    #   'JNJ', 'KO', 'JPM', 'MCD', 'MMM', 'MRK', 'MSFT', 'NKE', 'PG', 'TRV', 'UNH',\
    #   'CRM', 'VZ', 'V', 'WBA', 'WMT', 'DIS']
    
    other = ['EBAY', 'AMZN', 'GOOG', 'SNAP']
    stocks = list(np.unique(other))
    back = backtester(dow, LR_v1_predict, 3000, datetime(2021, 1, 1), datetime(2021, 1, 31), threshold = 1, sell_perc = 0.03, hold_till = 1,\
    stop_perc = 0.03)
    back.backtest()

    


    