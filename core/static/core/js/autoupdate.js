(function () {

"use strict";


const AutoUpdate = {

    interval: 5000,

    timer:null,

    busy:false,

    paused:false,


    init(){


        if(window.__AUTO_UPDATE__)
            return;


        window.__AUTO_UPDATE__ = true;


        this.bind();

        this.schedule();


    },


    schedule(){


        clearTimeout(this.timer);


        this.timer=setTimeout(
            ()=>this.refresh(),
            this.interval
        );


    },


    async refresh(){


        if(
            this.busy ||
            this.paused ||
            document.hidden
        ){

            this.schedule();
            return;

        }



        const elements =
            document.querySelectorAll(
                "[data-auto-update-url]"
            );


        if(!elements.length){

            this.schedule();
            return;

        }



        this.busy=true;



        try{


            for(
                const element of elements
            ){

                await this.updateElement(
                    element
                );

            }


        }


        catch(error){

            console.error(
                "Auto update error:",
                error
            );

        }


        finally{


            this.busy=false;


            this.schedule();


        }


    },



    async updateElement(element){


        const url =
            element.dataset.autoUpdateUrl;



        if(!url)
            return;



        const response =
            await fetch(
                url,
                {
                    method:"GET",

                    headers:{
                        "X-Requested-With":
                        "XMLHttpRequest",

                        "Cache-Control":
                        "no-cache"
                    },


                    cache:"no-store"

                }
            );



        if(!response.ok){

            throw new Error(
                response.status
            );

        }



        const html =
            await response.text();



        const old =
            element.innerHTML.trim();



        const fresh =
            html.trim();



        /*
          Update only if changed
        */

        if(
            old !== fresh
        ){

            element.innerHTML=fresh;


            element.dispatchEvent(
                new CustomEvent(
                    "autoUpdated"
                )
            );

        }


    },



    bind(){



        document.addEventListener(
            "visibilitychange",
            ()=>{

                if(
                    !document.hidden
                ){

                    this.refresh();

                }

            }
        );



        document.addEventListener(
            "submit",
            ()=>{

                this.paused=true;

                setTimeout(
                    ()=>{
                        this.paused=false;
                    },
                    3000
                );

            },
            true
        );



    }


};



document.addEventListener(
    "DOMContentLoaded",
    ()=>AutoUpdate.init()
);



window.AutoUpdate=AutoUpdate;


})();