#!/bin/bash -x 

KERNEL="`cat $HOME/Documents/bisection-tests/bisect-audio-kernel/kernel`"
MACHINE=10.153.104.231
USER=ubuntu


echo "Updating grub for $KERNEL and rebooting"
ssh $USER@$MACHINE sudo sed -i s/GRUB_DEFAULT=.*/GRUB_DEFAULT=\'\"${KERNEL}\"\'/ /etc/default/grub
ssh $USER@$MACHINE sudo update-grub
ssh $USER@$MACHINE sudo reboot 
echo "Waiting for reboot"
sleep 120
echo "Getting running kernel version"
ssh $USER@$MACHINE uname -a
echo "copying test script"
scp $HOME/Documents/audio-test/pa.py $USER@$MACHINE:
echo "Running test, this will be the exit code"
ssh -x $USER@$MACHINE ./pa.py -v
