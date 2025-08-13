import logging
import time

def load_unitree(unitree_ethernet: str):
    """
    Initialize the Unitree robot's network communication channel.
    
    This function sets up the Ethernet connection for a Unitree robot based on
    the provided configuration or environment variables. It can operate in either
    real hardware or simulation mode.
    
    Parameters
    ----------
    unitree_ethernet : str
        Configuration object containing the Unitree Ethernet adapter string, such as "eth0"
    
    Returns
    -------
    None
    
    Raises
    ------
    Exception
        If initialization of the Unitree Ethernet channel fails.
    """
    if unitree_ethernet is not None:
        logging.info(
            f"Using {unitree_ethernet} as the Unitree Network Ethernet Adapter"
        )
        from unitree.unitree_sdk2py.core.channel import ChannelFactoryInitialize
        
        try:
            ChannelFactoryInitialize(0, unitree_ethernet)
            
            # Add a delay to ensure the factory is fully initialized
            # This is important when multiple threads will be creating clients
            time.sleep(1.0)
            
            logging.info(f"Successfully initialized CycloneDDS using {unitree_ethernet}")
            
            # Test the initialization by creating a test client
            # This would fail early if there's an issue
            try:
                from unitree.unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient
                test_client = G1ArmActionClient()
                del test_client  # Clean up test client
                logging.info("Channel factory test successful [Arm Action]")
            except Exception as test_error:
                logging.warning(f"Channel factory test failed: {test_error}")

            try:
                from unitree.unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
                test_client = AudioClient()
                del test_client  # Clean up test client
                logging.info("Channel factory test successful [Audio]")
            except Exception as test_error:
                logging.warning(f"Channel factory test failed: {test_error}")

        except Exception as e:
            logging.error(f"Failed to initialize Unitree Ethernet channel: {e}")
            raise e
            
        logging.info(f"Booting Unitree and CycloneDDS using {unitree_ethernet}")