for ((i=1; i < 1000; i++)); do
        echo "===============$i=========="

        #step_1, power cycle card by relay
        sudo python3 ./Samanea_Scripts/Tool/Tool_RelayPowerOff.py
        sudo python3 ./Samanea_Scripts/Tool/Tool_RelayPowerOn.py
        
        #by I2C-Relay
        # echo "power cycle card..."
        # sfx-I2C-PF 0 0
        # sleep 1
        # sfx-I2C-PF 0 1


        #step_2, rescan card
        sudo /home/tcnsh/rescanpcie.sh
		sleep 5


        #step_3, test card ready or not
        #test bl3 by nvme
		# dev=$(sudo nvme list | grep nvme)

        #or test bl2 by check pcie
        dev=$(lspci -d cc53:)
        if [[ $dev == "" ]]; then
                echo "Device Not Ready"
                break;
        else
                echo $dev
        fi
done
