# myMC
A Python 3 port of [Ross Ridge's original Pubic Domain Python 2 code](http://www.csclub.uwaterloo.ca:11068/mymc/index.html).

Based on informal testing, the commands `check`, `delete`, `df`, `dir`, `export`, `import`, `ls` work.
These are enough to export and import saves.
I am not exactly sure what the other commands do so I cannot verify them.

I basically used 2to3 on the original Pubic Domain Python 2 code and then fixed the float division and bytes vs strings issues.
I did not have the necessary libraries for the UI so the GUI likely does not work.

## Exporting a save

Use the `dir` command to figure out the name of the save:

```bash
python3 mymc.py <path to the memory card .ps2 file> dir
```

You would see output like this:

```bash
    BASLUS-20678USAGAS00             UNLIMITED SAGA
     154KB Not Protected             SYSTEMDATA

    BADATA-SYSTEM                    Your System
       5KB Not Protected             Configuration

    BASLUS-20488-0000D               SOTET<13>060:08
     173KB Not Protected             Arias

    7,800 KB Free
```

### To export in EMS (.psu) format:

```bash
python3 mymc.py <path to the memory card .ps2 file> export BASLUS-20488-0000D
```

This creates a file named "BASLUS-20488-0000D.psu".

### To export in MAX Drive (.max) format:

```bash
python3 mymc.py <path to the memory card .ps2 file> export -m BASLUS-20488-0000D
```

This creates a file named "BASLUS-20488-0000D.max".
Note the "-m" option that appears after the `export` command.

## Importing a save

```bash
python3 mymc.py <path to the memory card .ps2 file> import <path to the save file>
```

You may need to use the `delete` command first to delete the save if it already exists on the memory card.

```bash
python3 mymc.py <path to the memory card .ps2 file> delete BASLUS-20488-0000D
```

## License

The original Python 2 code was placed in the public domain without a license.
I licensed the Python 3 port under a MIT License to make it clear you can do whatever you want with it.
