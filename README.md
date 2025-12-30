Make sure that open-ssh server is installed in your PC before proceeding.
On your Windows PC, right click on the folder to be shared. Go to Properties->Sharing->Advanced Sharing and check the 'Share this folder' option. Click Apply->OK. 
Mount the source folder using the following command, before running the code:

--> sudo mount -t cifs //(IP address of the server)/(Folder name that has been shared) /(path)/(to)/(mount)/in/your/pc -o username=$Winuser,password=$Winpass.

Replace $Winuser and $Winpass with the correspoding username and password of the Windows PC.

To unmount the folder:

--> sudo umount /(path)/(to)/(mount)/in/your/pc
