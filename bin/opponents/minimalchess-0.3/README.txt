MinimalChessEngine 0.3 - March 8, 2021
Author: Thomas Jahn (lithander@gmx.de)

MinimalChess is a barebones (minimal) implementation of a chess engine in C#.
It's estimated playing strenght is slightly above 1500 ELO on CCRL40/4.

Features:

* Implements the UCI protocol including the common time management options
* Iterative Deepening with Alpha-Beta pruning and Quiescence Search.
* Collects the Principal Variation (PV) of best moves in a Triangular PV-Table.
* Plays PV moves first, followed by MVV-LVA sorted captures.
* Positions are evaluated with Piece-Square Tables.

...that's all. 

My goal when writing the engine was to keep it as simple and as possible.

* The board is represented as an array of 64 squares. 
* The move generator is really straight forward. 
* There is no hash table, no undo-move method, just the essentials.
* The PSTs are defined in external files making it easy to tweak them or write your own. (Chose one them via UCI option)

It could be smaller or faster but I doubt it could be much more accessible than it currently is. ;)

The engine plays rather weak at slightly above 1500 ELO. Nothing to brag about but it makes it a good sparring partner for weak human players like myself and chess programmers who are just starting out.

You can find the source on Github:
	https://github.com/lithander/MinimalChessEngine

And I uploaded explanatory making-of videos on Youtube:
 	https://www.youtube.com/playlist?list=PL6vJSkTaZuBtTokp8-gnTsP39GCaRS3du 

Please let me know of any bugs or stability issues and must-have features you feel even the most barebones engine should support but MinimalChess is lacking.