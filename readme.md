This project aimed to provide a platform for developing trading strategies that work with online markets such as Binance and Forex. The main feature of this platform is that it enables strategy development without concern for complex issues like maintaining a stable connection to the markets, receiving real-time data, and opening and closing trades.

The following is a brief overview of each package in the project:

- **datasource**: Contains classes and modules for obtaining market data via web sockets and REST requests. Implementations for Binance and Forex are provided in the **bincpkg** and **frxpkg** packages, respectively. One can easily implement a data source for other markets with minor modifications.
    
- **dataprovider**: Retrieves raw data from the data source, saves them in a specific model in the database, and maintains historical data for analysis.
    
- **analysis**: Uses market data from the data provider to perform analyses, offering valuable insights into market trends.
    
- **decisioncenter**: Based on the analyzed data, this package makes trade decisions, such as opening new trades or closing existing ones.
    
- **market**: Provides functionalities for executing trades based on decisions made by the decision center. It also tracks updates on the current trade state.
    
- **models**: Database models and some specific classes based on the definitions are kept in this package.
    
- **modules**: Contains specialized modules like RabbitMQ connections, asynchronous sockets, and enumerations.
    
- **config**: Defines configuration classes for each trading strategy, which read and apply user-provided settings from the `/data/configs` directory.
    
- **utilities**: Provides various functionalities as static methods used by other classes.